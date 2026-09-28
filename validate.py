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

# Line sums must match to the cent. Only the final total may be rounded (cash rounding, e.g. IDR
# 334,011 printed as 334,000): up to 0.05% of the total. Measured on CORD, see results/M2_NOTES.md.
TOTAL_ROUNDING = Decimal('0.0005')


def close(a, b, rel=Decimal(0)):
    return abs(a - b) <= max(Decimal('0.01'), abs(b) * rel)


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
    """Re-read the printed dates with the date order the user confirmed for this vendor or country."""
    if order is None:
        return doc
    update = {}
    for field in ('issue_date', 'due_date'):
        d = read_date(getattr(doc, field + '_text'), order)
        if d is not None:
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

    if date_order is None:
        for field in ('issue_date', 'due_date'):
            if ambiguous(getattr(doc, field + '_text')):
                fail('date_ambiguous', [field], f'{getattr(doc, field + "_text")} could be day/month or month/day')

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
    if doc.subtotal is not None and amounts and None not in amounts:
        net = sum(i.amount - abs(i.discount or 0) for i in doc.items)
        # tax-inclusive prices: lines add up to subtotal + tax
        if not (close(net, doc.subtotal) or (tax and close(net, doc.subtotal + tax))):
            fail('items_sum', ['items', 'subtotal'], f'Line items add up to {net}, subtotal is {doc.subtotal}')

    if doc.subtotal is not None and doc.total is not None:
        expected = doc.subtotal + tax + (doc.service_charge or 0) - abs(doc.discount or 0)
        if not close(expected, doc.total, TOTAL_ROUNDING):
            fail('total_math', ['subtotal', 'tax', 'service_charge', 'discount', 'total'],
                 f'subtotal + tax + service - discount = {expected}, total is {doc.total}')
    elif doc.total is not None and amounts and None not in amounts:
        # no subtotal printed: the lines themselves must add up to the total.
        # ponytail: also accepts "tax already included", so a wrong tax is not caught here; tax_included field later
        net = sum(i.amount - abs(i.discount or 0) for i in doc.items)
        expected = net + tax + (doc.service_charge or 0) - abs(doc.discount or 0)
        if not (close(expected, doc.total, TOTAL_ROUNDING) or (tax and close(expected - tax, doc.total, TOTAL_ROUNDING))):
            fail('items_total', ['items', 'total'], f'Line items add up to {expected}, total is {doc.total}')

    for n, i in enumerate(doc.items):
        # ponytail: exact to 0.01; weighed items (0.235 kg x price) may need rounding room on invoices
        if None not in (i.quantity, i.unit_price, i.amount) and not close(i.quantity * i.unit_price, i.amount):
            fail('line_math', [f'items[{n}]'], f'{i.quantity} x {i.unit_price} = {i.quantity * i.unit_price}, line amount is {i.amount}')

    if doc.issue_date is not None and doc.issue_date > today:  # due dates are allowed in the future
        fail('date_future', ['issue_date'], f'Issue date {doc.issue_date} is in the future')
    if doc.issue_date and doc.due_date and doc.due_date < doc.issue_date:
        fail('due_before_issue', ['issue_date', 'due_date'], 'Due date is before issue date')

    if doc.currency is not None and doc.currency.upper() not in CURRENCIES:
        fail('currency_code', ['currency'], f'"{doc.currency}" is not an ISO 4217 currency code')

    return issues
