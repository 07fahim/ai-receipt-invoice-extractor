"""Deterministic checks on an extracted Document. No AI: a failed check sends the document to review."""
import re
from datetime import date
from decimal import Decimal

from schema import Document

# Active ISO 4217 codes
CURRENCIES = set("""
AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD BND BOB BRL BSD BTN BWP BYN BZD
CAD CDF CHF CLP CNY COP CRC CUP CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD
GNF GTQ GYD HKD HNL HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS KHR KMF KPW KRW KWD KYD KZT
LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN MYR MZN NAD NGN NIO NOK NPR
NZD OMR PAB PEN PGK PHP PKR PLN PYG QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE SOS SRD SSP
STN SVC SYP SZL THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX USD UYU UZS VES VND VUV WST XAF XCD XCG
XOF XPF YER ZAR ZMW ZWG
""".split())

# Line sums must match to the cent. Only the final total may be cash-rounded, and only by what its own rounding
# allows: a whole-number total (IDR 334,011 printed as 334,000) up to 0.05%, measured on CORD (results/M2_NOTES.md);
# a total in 5 cents (12.37 printed as 12.35, as in CHF, AUD, CAD) up to 2.5 cents; any other total to the cent.
# A flat 0.05% hid misread cents on USD invoices (978.12 read as 978.16), see results/M3_NOTES.md.
# Rounding to the nearest whole unit (404.36 taka printed as 404) always passes. A total printed with cents ("1,200.00")
# gets this room only in currencies whose cash is rounded to whole units (Shwapno: 816.15 printed "816.00") or when the
# currency is unknown (CORD test 41: 364,999.68 printed "365000.00", no currency on the receipt).
TOTAL_ROUNDING = Decimal('0.0005')
WHOLE_UNIT_CASH = {'BDT', 'INR', 'PKR', 'LKR', 'NPR', 'IDR', 'VND', 'JPY', 'KRW'}
CENTS_PRINTED = re.compile(r'[.,]\d{2}\s*$')

# VAT rates whose "VAT included" share can be recognised from the numbers alone (Bangladesh: 5, 7.5, 10, 15%).
# ponytail: Bangladeshi rates only; 20% added on top misread as 25% included would pass, so check before adding rates.
INCLUDED_VAT_RATES = (Decimal(5), Decimal('7.5'), Decimal(10), Decimal(15))


def close(a, b, rel=Decimal(0)):
    return abs(a - b) <= max(Decimal('0.01'), abs(b) * rel)


def included_share(tax, total, lines, whole_rounding=True):
    """True if the lines already add up to the total and tax is exactly the VAT inside it at a known rate (830 at 5%
    holds 39.52), whatever the model said. Without the lines, 10% on top with the subtotal read as the total
    (tax 15,000, total 165,000) would look the same."""
    return (lines is not None and total_close(lines, total, whole_rounding)
            and any(abs(tax - total * r / (100 + r)) <= Decimal('0.01') for r in INCLUDED_VAT_RATES))


def total_close(expected, total, whole_rounding=True):
    """expected (from the lines or the subtotal) matches the printed total, allowing only the total's own rounding."""
    if whole_rounding and total == total.to_integral_value():
        return abs(expected - total) <= max(Decimal('0.5'), abs(total) * TOTAL_ROUNDING)
    return abs(expected - total) <= (Decimal('0.025') if total * 20 == (total * 20).to_integral_value() else Decimal('0.01'))


PRINTED_NUMBER = re.compile(r'\d[\d.,\s]*\d|\d')
THREE_DECIMAL_CURRENCIES = {'BHD', 'IQD', 'JOD', 'KWD', 'LYD', 'OMR', 'TND'}


def thousands_read_as_decimals(text, amount):
    """The printed amount if it ends in a separator + exactly 3 digits ('22.000', '·7,000', '1.250.000') and the
    extracted amount read those 3 digits as decimals (22, 7, 1250); None otherwise. The arithmetic checks cannot see
    this: every amount on the document shrinks by the same factor."""
    numbers = PRINTED_NUMBER.findall(text or '')
    if not numbers or amount is None:
        return None
    printed = max(numbers, key=lambda n: sum(c.isdigit() for c in n)).replace(' ', '')
    head, sep, tail = printed[:-4], printed[-4:-3], printed[-3:]
    if sep not in ('.', ',') or not tail.isdigit() or not re.sub(r'\D', '', head).lstrip('0'):
        return None  # '0.500' is half, never five hundred
    as_decimals = Decimal(re.sub(r'\D', '', head) + '.' + tail)
    return printed if amount == as_decimals else None


NUMERIC_DATE = re.compile(r'\b(\d{1,2})[./-](\d{1,2})[./-](\d{4}|\d{2})\b')


def ambiguous(text):
    """True for printed dates like 05/11/2021 that read differently as day/month and month/day."""
    m = NUMERIC_DATE.search(text or '')
    return bool(m) and int(m[1]) <= 12 and int(m[2]) <= 12 and int(m[1]) != int(m[2])


def read_date(text, order):
    """Printed numeric date in a known order ('MDY' US, 'DMY' most other countries); None if it can't be read."""
    assert order in ('MDY', 'DMY'), order
    m = NUMERIC_DATE.search(text or '')
    if not m:
        return None
    a, b, y = int(m[1]), int(m[2]), int(m[3])
    y += 2000 if y < 100 else 0
    month, day = (a, b) if order == 'MDY' else (b, a)
    try:
        return date(y, month, day)
    except ValueError:
        return None


def apply_date_order(doc: Document, order: str | None) -> Document:
    """Re-read the printed dates with the date order the user confirmed for this vendor or country. A date the user
    typed (not one of the two readings of the printed text) is kept."""
    if order is None:
        return doc
    update = {}
    for field in ('issue_date', 'due_date'):
        text, current = getattr(doc, field + '_text'), getattr(doc, field)
        d = read_date(text, order)
        if d is not None and current in (None, read_date(text, 'MDY'), read_date(text, 'DMY')):
            update[field] = d
    return doc.model_copy(update=update)


def validate(doc: Document, today: date | None = None, date_order: str | None = None) -> list[dict]:
    """Return failed checks as {'check', 'fields', 'message'}. Empty list = passed.
    Checks with missing inputs are skipped, except a missing total.
    date_order: 'MDY' or 'DMY' when known for this vendor; otherwise ambiguous dates are flagged."""
    today = today or date.today()
    doc = apply_date_order(doc, date_order)
    issues = []

    def fail(check, fields, message):
        issues.append({'check': check, 'fields': fields, 'message': message})

    if doc.is_document is False:  # one clear message instead of "No total found" and friends
        fail('is_document', [], "This doesn't look like a receipt or invoice")
        return issues

    if date_order is None:
        for field in ('issue_date', 'due_date'):
            if ambiguous(getattr(doc, field + '_text')):
                fail('date_ambiguous', [field], f'{getattr(doc, field + "_text")} could be day/month or month/day')

    if (doc.document_count or 1) > 1:
        fail('one_document', [], f'This file seems to contain {doc.document_count} documents; upload one per file')

    if doc.total is None:
        fail('total_present', ['total'], 'No total found')

    printed = thousands_read_as_decimals(doc.total_text, doc.total)
    if printed and (doc.currency or '').upper() not in THREE_DECIMAL_CURRENCIES:
        whole = Decimal(re.sub(r'\D', '', printed))
        fail('total_format', ['total'], f'Total printed as {printed}: is it {whole:,} rather than {doc.total}?')

    if not doc.items and (doc.total or doc.subtotal):
        fail('items_missing', ['items'], 'Amounts found but no line items')

    tax = doc.tax or 0
    amounts = [i.amount for i in doc.items]
    net = sum(i.amount - abs(i.discount or 0) for i in doc.items) if amounts and None not in amounts else None
    if doc.subtotal is not None and net is not None:
        # tax-inclusive prices: lines add up to subtotal + tax
        gross = sum(amounts)  # item discounts listed apart, already inside the discount line
        if not (close(net, doc.subtotal) or close(gross, doc.subtotal) or (tax and close(net, doc.subtotal + tax))):
            fail('items_sum', ['items', 'subtotal'], f'Line items add up to {net}, subtotal is {doc.subtotal}')

    whole = not CENTS_PRINTED.search(doc.total_text or '') or doc.currency is None or doc.currency.upper() in WHOLE_UNIT_CASH
    near = lambda expected: total_close(expected, doc.total, whole)

    # The same discount on an item and on the receipt ("Disc -100% (ITM06)" then SUBTTL): the lines already hold it
    twice = bool(doc.discount) and net is not None and close(sum(abs(i.discount or 0) for i in doc.items), abs(doc.discount))

    # Tax added on top is always accepted. "VAT included" (tax already inside the prices) only when the model says so
    # or the numbers prove it (included_share): the arithmetic decides, so a wrong tax_included=True on an invoice
    # whose tax is added on top does no harm.
    if doc.subtotal is not None and doc.total is not None:
        discount = 0 if twice and close(net, doc.subtotal) else abs(doc.discount or 0)
        expected = doc.subtotal + tax + (doc.service_charge or 0) - discount
        included = tax and near(expected - tax) and (doc.tax_included or included_share(tax, doc.total, net, whole))
        if not (near(expected) or included):
            fail('total_math', ['subtotal', 'tax', 'service_charge', 'discount', 'total'],
                 f'subtotal + tax + service - discount = {expected}, total is {doc.total}')
    elif doc.total is not None and net is not None:
        # no subtotal printed: the lines themselves must add up to the total. Unless the model says the tax is
        # added on top (tax_included False), both readings are accepted, so a wrong tax is not always caught here.
        expected = net + tax + (doc.service_charge or 0) - (0 if twice else abs(doc.discount or 0))
        included = tax and near(expected - tax) and (doc.tax_included is not False or included_share(tax, doc.total, net, whole))
        if not (near(expected) or included):
            fail('items_total', ['items', 'total'], f'Line items add up to {expected}, total is {doc.total}')

    for n, i in enumerate(doc.items):
        # a weight printed as 1.03 kg may be 1.034 kg: allow for its rounding, half the last printed step
        if None in (i.quantity, i.unit_price, i.amount):
            continue
        room = abs(i.unit_price) * Decimal('0.005') if i.quantity != i.quantity.to_integral_value() else 0
        if abs(i.quantity * i.unit_price - i.amount) > max(Decimal('0.01'), room):
            fail('line_math', [f'items[{n}]'], f'{i.quantity} x {i.unit_price} = {i.quantity * i.unit_price}, line amount is {i.amount}')

    if doc.issue_date is not None and doc.issue_date > today:  # due dates are allowed in the future
        fail('date_future', ['issue_date'], f'Issue date {doc.issue_date} is in the future')
    if doc.issue_date and doc.due_date and doc.due_date < doc.issue_date:
        fail('due_before_issue', ['issue_date', 'due_date'], 'Due date is before issue date')

    if doc.currency is not None and doc.currency.upper() not in CURRENCIES:
        fail('currency_code', ['currency'], f'"{doc.currency}" is not an ISO 4217 currency code')

    return issues


SUM_CHECKS = {'total_format', 'items_sum', 'total_math', 'items_total', 'line_math'}
DOC_AMOUNTS = ('subtotal', 'discount', 'tax', 'service_charge', 'total')
ITEM_AMOUNTS = ('unit_price', 'amount', 'discount')


def suggest(doc: Document, date_order: str | None = None) -> dict | None:
    """A correction for the review screen, never applied by itself: all amounts x1000 when thousands were read as
    decimals, or one misread digit. Only when exactly one such change makes every sum check pass, and for a digit only
    when two different sum checks failed: on planted mistakes that gave 384 right suggestions and 0 wrong, while
    one failed check allowed coincidental fixes (a dropped line 'repaired' by changing another; 52 wrong of 333).
    None otherwise.
    Returns {'message', 'changes': [{'field', 'from', 'to'}]} with fields like 'total' or 'items[2].amount'."""
    def sums_fail(d):
        return {i['check'] for i in validate(d, date_order=date_order)} & SUM_CHECKS

    failing = sums_fail(doc)
    if not failing:
        return None
    amounts = [(f, getattr(doc, f)) for f in DOC_AMOUNTS if getattr(doc, f) is not None] + [
        (f'items[{n}].{f}', getattr(i, f)) for n, i in enumerate(doc.items) for f in ITEM_AMOUNTS if getattr(i, f) is not None]

    def changed(updates):
        top = {f: v for f, v in updates.items() if not f.startswith('items[')}
        items = [i.model_copy(update={f.split('.')[1]: v for f, v in updates.items() if f.startswith(f'items[{n}].')})
                 for n, i in enumerate(doc.items)]
        return doc.model_copy(update={**top, 'items': items})

    if 'total_format' in failing:
        updates = {f: v * 1000 for f, v in amounts}
        if sums_fail(changed(updates)):
            return None
        return {'message': f'Thousands were read as decimals: every amount x1,000 (total {doc.total} becomes {doc.total * 1000:,})',
                'changes': [{'field': f, 'from': str(v), 'to': str(updates[f])} for f, v in amounts]}

    if len(failing) < 2 or len(amounts) > 100:  # the search grows with amounts squared: 100 amounts take about a second
        return None
    found = []
    for field, value in amounts:
        text = format(value, 'f')
        for pos, old in enumerate(text):
            for new in '0123456789' if old.isdigit() else ():
                if new == old:
                    continue
                candidate = Decimal(text[:pos] + new + text[pos + 1:])
                if not sums_fail(changed({field: candidate})):
                    found.append((field, value, candidate))
                    if len(found) > 1:
                        return None  # two different fixes both fit: the numbers can't tell which is right
    if not found:
        return None
    field, value, candidate = found[0]
    return {'message': f'Did you mean {candidate} instead of {value}? It is the only one-digit change that makes every sum add up',
            'changes': [{'field': field, 'from': str(value), 'to': str(candidate)}]}
