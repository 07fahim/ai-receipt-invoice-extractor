import re
import string
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

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
# allows: rupiah, dong and won totals rounded to hundreds (IDR 334,011 printed as 334,000) up to 0.05%, measured on
# CORD (results/M2_NOTES.md); taka, rupees and totals printed without cents rounded to whole units (404.36 taka
# printed as 404) or cut by less than one (a BPDB bill cuts 9,983,196.70 to 9,983,196.00 and carries the rest);
# a total in 5 cents (12.37 printed as 12.35) up to 2.5 cents in the currencies whose cash is rounded so (CHF, AUD,
# CAD, ...; EUR too, though only some euro countries round, so a 2-cent euro misread can pass); any other total to
# the cent. A flat 0.05% hid misread cents on USD invoices (978.12 read
# as 978.16, results/M3_NOTES.md), 5 cents of room hid 977.50 read for 977.52 in USD, and 0.05% hid 400 taka on a
# 977,500 taka total. A total printed with cents ("1,200.00") gets whole-unit room only in currencies whose cash is
# rounded to whole units (Shwapno: 816.15 printed "816.00"). No currency on the receipt (CORD) keeps all the room.
TOTAL_ROUNDING = Decimal('0.0005')
WHOLE_UNIT_CASH = {'BDT', 'INR', 'PKR', 'LKR', 'NPR', 'IDR', 'VND', 'JPY', 'KRW'}
HUNDREDS_CASH = {'IDR', 'VND', 'KRW'}
FIVE_CENT_CASH = {'CHF', 'AUD', 'NZD', 'CAD', 'SGD', 'MYR', 'EUR', 'ZAR'}
CENTS_PRINTED = re.compile(r'[.,]\d{2}\s*$')

# VAT rates whose "VAT included" share can be recognised from the numbers alone (Bangladesh: 5, 7.5, 10, 15%).
# Bangladeshi rates only: 20% added on top misread as 25% included would pass, so check before adding rates.
INCLUDED_VAT_RATES = (Decimal(5), Decimal('7.5'), Decimal(10), Decimal(15))

# Rates a "VAT included" tax may be the share of, when the document prints none. A share at no rate (6.00 of 40.50,
# 17%) is a misread. 25% is left out: 20% added on top with the subtotal read as the total looks like 25% included.
# The share may be of the total or of the subtotal (a tip or service charge without VAT added after it).
VAT_RATES = tuple(map(Decimal, '2.6 3.8 5 6 7 7.5 8 8.1 9 10 11 12 13 14 15 16 17 17.5 18 19 20 21 22 23 24'.split()))

# Where "VAT included" receipts are the norm and one receipt mixes rates (7% and 19% in Germany, 8% and 10% in Japan,
# 0% food and 20% in the UK), any share up to the top rate may be a mix, unless the tax is exactly one of the
# country's rates of the total: that is tax added on top with the subtotal read as the total (10.00 on 100.00), which
# a mix almost never gives (4.15 on 29.15). Euro countries by the VAT number's prefix, else all euro rates.
# Invoices don't get this: they add the tax on top (736 of 737 saved invoice readings), and two rates on top look
# exactly like a mix. A known country's own rates also count as exact, and euro rates on euro documents (25% only
# for a known country: 20% on top looks exactly like 25%).
VAT_BY = {k: tuple(map(Decimal, v.split())) for k, v in {
    'GBP': '5 20', 'CHF': '2.6 3.8 8.1', 'JPY': '8 10', 'SEK': '6 12 25', 'NOK': '12 15 25', 'DKK': '25', 'ISK': '11 24',
    'AT': '10 13 20', 'BE': '6 12 21', 'CY': '5 9 19', 'DE': '7 19', 'EE': '9 13 24', 'EL': '6 13 24', 'ES': '4 10 21',
    'FI': '10 14 25.5', 'FR': '5.5 10 20', 'HR': '5 13 25', 'IE': '9 13.5 23', 'IT': '4 5 10 22', 'LT': '5 9 21',
    'LU': '3 8 14 17', 'LV': '5 12 21', 'MT': '5 7 18', 'NL': '9 21', 'PT': '6 13 23', 'SI': '5 9.5 22', 'SK': '5 19 23'}.items()}
VAT_BY['EUR'] = tuple(sorted({r for k, rates in VAT_BY.items() if len(k) == 2 for r in rates}))

# countries where a seller VAT/GST number is expected: BIN (BDT), GSTIN (INR), UK VAT (GBP), EU VAT (EUR)
VAT_ID_EXPECTED = {'BDT', 'INR', 'GBP', 'EUR'}


def close(a, b, rel=Decimal(0)):
    return abs(a - b) <= max(Decimal('0.01'), abs(b) * rel)


def included_share(tax, total, lines, allow=frozenset()):
    # 830 at 5% holds 39.52; without the lines, 10% on top with the subtotal read as the total looks the same
    return (lines is not None and total_close(lines, total, allow)
            and any(abs(tax - total * r / (100 + r)) <= Decimal('0.01') for r in INCLUDED_VAT_RATES))


def vat_share(tax, bases, currency=None, tax_id=None, doc_type=None):
    c = (currency or '').upper()
    m = re.search(r'([A-Z]{2})[A-Z]?\d', re.sub(r'[\s.-]', '', (tax_id or '').upper()))  # the letters before the digits: ATU123 -> AT
    prefix = m[1] if m else ''
    country = prefix if c == 'EUR' and prefix in VAT_BY else c
    own = tuple(r for r in VAT_BY['EUR'] if r != 25) if country == 'EUR' else VAT_BY.get(country, ())
    if any(abs(tax - b * r / (100 + r)) <= CENT for b in bases for r in VAT_RATES + own):
        return True
    rates = VAT_BY.get(country)
    if doc_type == 'invoice' or not rates or tax <= 0 or any(abs(tax - b * r / 100) <= CENT for b in bases for r in rates):
        return False
    return any(tax <= b * max(rates) / (100 + max(rates)) + CENT for b in bases)


def cash_rounding(currency, total_text):
    # the roundings a printed total may carry, see TOTAL_ROUNDING
    c = (currency or '').upper()
    if not c:
        return {'whole', 'hundreds', 'five'}
    whole = c in WHOLE_UNIT_CASH or (total_text and not CENTS_PRINTED.search(total_text))
    return {k for k, on in (('whole', whole), ('hundreds', c in HUNDREDS_CASH), ('five', c in FIVE_CENT_CASH)) if on}


def total_close(expected, total, allow=frozenset()):
    gap = abs(expected - total)
    if 'whole' in allow and total == total.to_integral_value():
        if 'hundreds' in allow and gap <= abs(total) * TOTAL_ROUNDING:
            return True
        over = abs(total) - abs(expected)  # rounded up by half a unit at most, or cut by less than one
        return -1 < over <= Decimal('0.5')
    return gap <= (Decimal('0.025') if 'five' in allow and total * 20 == (total * 20).to_integral_value() else Decimal('0.01'))


PRINTED_NUMBER = re.compile(r'\d[\d.,\s]*\d|\d')
THREE_DECIMAL_CURRENCIES = {'BHD', 'IQD', 'JOD', 'KWD', 'LYD', 'OMR', 'TND'}


def thousands_read_as_decimals(text, amount):
    # '22.000' read as 22: every amount shrinks by the same factor, so the sum checks can't see it
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
    m = NUMERIC_DATE.search(text or '')
    return bool(m) and int(m[1]) <= 12 and int(m[2]) <= 12 and int(m[1]) != int(m[2])


def read_date(text, order):
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
    # a date the user typed (not one of the two readings) is kept
    if order is None:
        return doc
    update = {}
    for field in ('issue_date', 'due_date'):
        text, current = getattr(doc, field + '_text'), getattr(doc, field)
        d = read_date(text, order)
        if d is not None and current in (None, read_date(text, 'MDY'), read_date(text, 'DMY')):
            update[field] = d
    return doc.model_copy(update=update)


def num(d):
    if d == d.to_integral_value():
        return f'{int(d):,}'
    d = d.normalize()
    return f'{d:,f}' if d.as_tuple().exponent < -2 else f'{d:,.2f}'  # weighed items keep their 3 decimals


CENT = Decimal('0.01')


def pct(r):
    return f'{r.normalize():f}'  # 15, 8.5, 0


def review(issues):
    # notes are shown on the document but never send it to review
    return [i for i in issues if i.get('level') != 'note']


def older_than_upload(issue_date, others):
    # a stray old receipt in a current batch; a whole backlog uploaded together never triggers it
    if issue_date is None or len(others) < 3:
        return None
    middle = sorted(others)[len(others) // 2]
    if (middle - issue_date).days <= 183:
        return None
    return {'message': f'This document is dated {issue_date:%m/%Y}. The rest of this upload is from {middle:%m/%Y}.',
            'check': 'older_than_upload', 'fields': ['issue_date'], 'level': 'note'}


B36 = string.digits + string.ascii_uppercase
GSTIN = re.compile(r'\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]')


def gstin_valid(s):
    # state code 01-38, then the GST mod-36 check character
    if not GSTIN.fullmatch(s) or not 1 <= int(s[:2]) <= 38:
        return False
    total = 0
    for n, ch in enumerate(s[:14]):
        p = B36.index(ch) * (2 if n % 2 else 1)
        total += p // 36 + p % 36
    return B36[(36 - total % 36) % 36] == s[14]


def uk_vat_valid(digits):
    # HMRC mod-97: the old scheme or the new one (+55)
    total = sum(w * int(c) for w, c in zip(range(8, 1, -1), digits[:7])) + int(digits[7:9])
    return total % 97 == 0 or (total + 55) % 97 == 0


def tax_id_problem(raw, currency=None):
    # only formats with a public check digit; a Bangladeshi BIN or other EU numbers are not checked.
    # UK receipts often print the number without GB ("VAT Reg No: 191 2478 96")
    s = re.sub(r'[\s.-]', '', raw or '').upper()
    if (currency or '').upper() == 'GBP' and re.fullmatch(r'\d{9}|\d{12}', s):
        s = 'GB' + s
    if re.fullmatch(r'GB(\d{9}|\d{12})', s):
        return None if uk_vat_valid(s[2:11]) else f'{raw} is not a valid UK VAT number. Check it on the document.'
    if len(s) == 15 and s[:2].isdigit() and s[13] == 'Z':
        return None if gstin_valid(s) else f'{raw} is not a valid GSTIN. Check it on the document.'
    return None


def line_net(doc: Document):
    # the lines after their own discounts; None when a line has no amount
    amounts = [i.amount for i in doc.items]
    return sum(i.amount - abs(i.discount or 0) for i in doc.items) if amounts and None not in amounts else None


def validate(doc: Document, today: date | None = None, date_order: str | None = None) -> list[dict]:
    # checks with missing inputs are skipped, except a missing total
    today = today or date.today()
    doc = apply_date_order(doc, date_order)
    issues = []

    def fail(check, fields, message, level=None):
        issues.append({'check': check, 'fields': fields, 'message': message, **({'level': level} if level else {})})

    if doc.is_document is False:  # one clear message instead of "No total found" and friends
        fail('is_document', [], "This doesn't look like a receipt or invoice.")
        return issues

    if date_order is None:
        for field in ('issue_date', 'due_date'):
            if ambiguous(getattr(doc, field + '_text')):
                fail('date_ambiguous', [field], f'Is {getattr(doc, field + "_text")} day first or month first?')

    if (doc.document_count or 1) > 1:
        fail('one_document', [], f'This file seems to hold {doc.document_count} documents. Upload one per file.')

    if doc.total is None:
        fail('total_present', ['total'], 'No total found.')

    printed = thousands_read_as_decimals(doc.total_text, doc.total)
    if printed and (doc.currency or '').upper() not in THREE_DECIMAL_CURRENCIES:
        whole = Decimal(re.sub(r'\D', '', printed))
        fail('total_format', ['total'], f'The total is printed as {printed}. Is it {num(whole)}?')

    if not doc.items and (doc.total or doc.subtotal):
        fail('items_missing', ['items'], 'There are amounts but no line items.')

    tax = doc.tax or 0
    amounts = [i.amount for i in doc.items]
    net = line_net(doc)
    if doc.subtotal is not None and net is not None:
        # tax-inclusive prices: lines add up to subtotal + tax
        gross = sum(amounts)  # item discounts listed apart, already inside the discount line
        if not (close(net, doc.subtotal) or close(gross, doc.subtotal) or (tax and close(net, doc.subtotal + tax))):
            fail('items_sum', ['items', 'subtotal'], f'Line items add up to {num(net)}. The subtotal is {num(doc.subtotal)}.')

    allow = cash_rounding(doc.currency, doc.total_text)
    near = lambda expected: total_close(expected, doc.total, allow)

    # The same discount on an item and on the receipt ("Disc -100% (ITM06)" then SUBTTL): the lines already hold it
    twice = bool(doc.discount) and net is not None and close(sum(abs(i.discount or 0) for i in doc.items), abs(doc.discount))
    # subtotal already has the discount taken off: don't subtract it again (CORD test 33, used below and by tax_rate)
    discount_in_subtotal = twice and doc.subtotal is not None and close(net, doc.subtotal)

    # Tax added on top is always accepted. "VAT included" (tax already inside the prices) only when the model says so
    # or the numbers prove it (included_share): the arithmetic decides, so a wrong tax_included=True on an invoice
    # whose tax is added on top does no harm.
    # VAT summary rows, read before the included decision so both it and the row checks below use them
    rows = [r for r in doc.vat_lines if None not in (r.rate, r.net, r.tax)]

    if doc.subtotal is not None and doc.total is not None:
        discount = 0 if discount_in_subtotal else abs(doc.discount or 0)
        expected = doc.subtotal + tax + (doc.service_charge or 0) - discount
        # a printed rate whose included share matches the tax is proof on its own, no line total needed
        # (VAT/GST only: a US sales tax subtotal misread as the total would pass the same arithmetic by chance)
        printed = doc.tax_kind in ('vat', 'gst') and doc.tax_rate and abs(
            tax - doc.total * doc.tax_rate / (100 + doc.tax_rate)) <= Decimal('0.01')
        # with rows printed, the total being the rows' gross is proof on its own; without rows, fall back as before
        row_share = near(sum(r.net + r.tax for r in rows)) if rows else (
            doc.tax_included and vat_share(tax, (doc.total, doc.subtotal), doc.currency, doc.seller_tax_id, doc.doc_type))
        included = tax and near(expected - tax) and (printed or row_share or included_share(tax, doc.total, net, allow))
        if not (near(expected) or included):
            fail('total_math', ['subtotal', 'tax', 'service_charge', 'discount', 'total'],
                 f'Subtotal + tax + service - discount = {num(expected)}. The total is {num(doc.total)}.')
    elif doc.total is not None and net is not None:
        # no subtotal printed: the lines themselves must add up to the total. Unless the model says the tax is
        # added on top (tax_included False), both readings are accepted, so a wrong tax is not always caught here.
        expected = net + tax + (doc.service_charge or 0) - (0 if twice else abs(doc.discount or 0))
        included = tax and near(expected - tax) and (doc.tax_included is not False or included_share(tax, doc.total, net, allow))
        if not (near(expected) or included):
            fail('items_total', ['items', 'total'], f'Line items add up to {num(expected)}. The total is {num(doc.total)}.')

    # Printed rates: the shop's own arithmetic, so no fix is ever suggested for these. VAT/GST is charged on the
    # amount after the discount (HMRC VAT Notice 700 for basic discounts), with or without the service charge,
    # added on top or included in the prices. US sales tax can skip exempt items: only too much tax is flagged.
    if doc.tax_rate is not None and doc.tax is not None and doc.subtotal is not None and doc.tax_kind:
        rate = doc.tax_rate / 100
        base = doc.subtotal if discount_in_subtotal else doc.subtotal - abs(doc.discount or 0)
        room = Decimal('1') if doc.tax == doc.tax.to_integral_value() else CENT * max(1, len(doc.items))
        if doc.tax_kind in ('vat', 'gst'):
            bases = [base] + ([base + doc.service_charge] if doc.service_charge else [])
            if not any(abs(doc.tax - b * rate) <= room or abs(doc.tax - b * rate / (1 + rate)) <= room for b in bases):
                fail('tax_rate', ['tax'], f'{doc.tax_kind.upper()} {pct(doc.tax_rate)}% of {num(base)} is '
                     f'{num((base * rate).quantize(CENT, ROUND_HALF_UP))}. The document says {num(doc.tax)}.')
        else:
            base = doc.subtotal + (doc.service_charge or 0)
            top = base * rate
            if (rate == 0 and doc.tax > 0) or doc.tax > top + room:
                fail('tax_rate', ['tax'], f'Tax {pct(doc.tax_rate)}% of {num(base)} is at most '
                     f'{top.quantize(CENT, ROUND_HALF_UP):,.2f}. The document says {num(doc.tax)}.')  # 0.00, never 0
    # VAT summary rows: each row's own tax must match its rate and net, and the rows must add up to doc.tax.
    # Whole-unit room (like doc.tax above) for currencies with no cents, or an unknown currency whose row tax
    # is itself a whole number (e.g. a JPY/IDR row printed or rounded to whole units); otherwise a flat cent
    # of room per item.
    for r in rows:
        whole = (doc.currency or '').upper() in WHOLE_UNIT_CASH or (not doc.currency and r.tax == r.tax.to_integral_value())
        room = Decimal('1') if whole else CENT * max(1, len(doc.items))
        if abs(r.tax - r.net * r.rate / 100) > room or (r.gross is not None and abs(r.net + r.tax - r.gross) > CENT):
            fail('vat_row', ['tax'], f'The {pct(r.rate)}% VAT row: {pct(r.rate)}% of {num(r.net)} is '
                 f'{num((r.net * r.rate / 100).quantize(CENT, ROUND_HALF_UP))}. It says {num(r.tax)}.')
    if rows and doc.tax is not None and abs(sum(r.tax for r in rows) - doc.tax) > CENT * len(rows):
        fail('vat_rows_tax', ['tax'], f'The VAT rows add up to {num(sum(r.tax for r in rows))}. The tax is {num(doc.tax)}.')

    if doc.discount_rate is not None and doc.discount and doc.subtotal is not None:
        most = doc.subtotal * doc.discount_rate / 100
        if abs(doc.discount) > most + CENT:
            fail('discount_rate', ['discount'], f'{pct(doc.discount_rate)}% of {num(doc.subtotal)} is '
                 f'{num(most.quantize(CENT, ROUND_HALF_UP))}. The discount is {num(abs(doc.discount))}.')

    problem = tax_id_problem(doc.seller_tax_id, doc.currency)
    if problem:
        fail('tax_id_invalid', ['seller_tax_id'], problem)
    if doc.tax_kind in ('vat', 'gst') and doc.tax and not doc.seller_tax_id and (doc.currency or '').upper() in VAT_ID_EXPECTED:
        name, label = ('GST', 'GSTIN') if doc.tax_kind == 'gst' else ('VAT', 'VAT number')
        fail('tax_id_missing', ['seller_tax_id'], f'No seller {label} found. It is needed to claim this {name} back.', 'note')

    for n, i in enumerate(doc.items):
        # a weight printed as 1.03 kg may be 1.034 kg: allow for its rounding, half the last printed step
        if None in (i.quantity, i.unit_price, i.amount):
            continue
        room = abs(i.unit_price) * Decimal('0.005') if i.quantity != i.quantity.to_integral_value() else 0
        if abs(i.quantity * i.unit_price - i.amount) > max(Decimal('0.01'), room):
            fail('line_math', [f'items[{n}]'], f'{num(i.quantity)} x {num(i.unit_price)} = {num(i.quantity * i.unit_price)}. The line says {num(i.amount)}.')

    # one day of room: the server's date (UTC) is behind Dhaka until 06:00; due dates may be in the future
    if doc.issue_date is not None and doc.issue_date > today + timedelta(days=1):
        fail('date_future', ['issue_date'], f'The issue date {doc.issue_date} is in the future.')
    if doc.issue_date and doc.due_date and doc.due_date < doc.issue_date:
        fail('due_before_issue', ['issue_date', 'due_date'], 'The due date is before the issue date.')

    if doc.currency is not None and doc.currency.upper() not in CURRENCIES:
        fail('currency_code', ['currency'], f'"{doc.currency}" is not a currency code.')

    return issues


def one_digit_changes(value):
    text = format(value, 'f')
    for pos, old in enumerate(text):
        for new in '0123456789' if old.isdigit() else ():
            if new != old:
                yield Decimal(text[:pos] + new + text[pos + 1:])


SUM_CHECKS = {'total_format', 'items_sum', 'total_math', 'items_total', 'line_math'}
DOC_AMOUNTS = ('subtotal', 'discount', 'tax', 'service_charge', 'total')
ITEM_AMOUNTS = ('unit_price', 'amount', 'discount')


def suggest(doc: Document) -> dict | None:
    # never applied by itself. A digit fix needs two failed sum checks: on planted mistakes
    # that gave 384 right and 0 wrong; with one failed check, 52 of 333 were wrong
    def sums_fail(d, issues=None):
        return {i['check'] for i in issues or validate(d)} & SUM_CHECKS  # dates play no part in the sums

    issues = validate(doc)  # once: the quantity rule below reads the same list
    failing = sums_fail(doc, issues)
    if not failing:
        return None
    amounts = [(f, getattr(doc, f)) for f in DOC_AMOUNTS if getattr(doc, f) is not None] + [
        (f'items[{n}].{f}', getattr(i, f)) for n, i in enumerate(doc.items) for f in ITEM_AMOUNTS if getattr(i, f) is not None]

    def changed(updates):
        top = {f: v for f, v in updates.items() if not f.startswith('items[')}
        items = [i.model_copy(update={f.split('.')[1]: v for f, v in updates.items() if f.startswith(f'items[{n}].')})
                 for n, i in enumerate(doc.items)]
        return doc.model_copy(update={**top, 'items': items})

    if 'total_format' in failing:  # decides alone: the rules below never run when the total looks 1,000 times off
        updates = {f: v * 1000 for f, v in amounts}
        after = sums_fail(changed(updates))
        if 'total_format' in after or not after <= failing:  # other sums may still fail, but x1000 must not add one
            return None
        return {'message': f'The amounts look 1,000 times too small. The total would be {num(doc.total * 1000)}.',
                'changes': [{'field': f, 'from': str(v), 'to': str(updates[f])} for f, v in amounts]}

    # A weighed item read as a whole quantity (1.89 lb @ 19.50 = 36.86 read as 1 x 19.50): the quantity with the fewest
    # decimals (up to 3) that gives the amount to the cent, if only one does. The line check's own room would let
    # almost any 3-decimal quantity fit. A quantity already read with decimals is left alone: on WildReceipt the
    # wrong number was the unit price (1.76 lb @ 0.99/3 lb) or a digit of it (6.281 gal for 6.201).
    # Checked first; if the digit search also finds a fix, neither is shown. Nor when one digit of the price would
    # make the line add up too (4 x 125 for 4 x 185 is no weighed item): on planted price misreads that was 3,133
    # wrong quantities, 0 right.
    found = []
    lines = [i['fields'][0] for i in issues if i['check'] == 'line_math']
    n = int(lines[0][6:-1]) if len(lines) == 1 else None
    item = doc.items[n] if n is not None else None
    if item and item.quantity > 0 and item.quantity == item.quantity.to_integral_value() and item.unit_price > 0 and item.amount > 0:
        for places in range(4):
            step = Decimal(1).scaleb(-places)
            q = (item.amount / item.unit_price).quantize(step)
            fits = [c for c in (q - step, q, q + step) if c > 0 and abs(c * item.unit_price - item.amount) <= Decimal('0.005')]
            if fits:
                break
        field = f'items[{n}].quantity'
        price_fits = any(abs(item.quantity * p - item.amount) <= Decimal('0.005') for p in one_digit_changes(item.unit_price))
        if len(fits) == 1 and fits[0] != item.quantity and not price_fits and not sums_fail(changed({field: fits[0]})):
            q = Decimal(format(fits[0].normalize(), 'f'))
            found.append((field, item.quantity, q, f'{item.description or f"Line {n + 1}"}: is the quantity {num(q)}? Then the line adds up.'))

    # The search grows with amounts squared: 33 amounts took 0.45 s, 99 took 2.9 s (laptop, 2026-10-02),
    # and it runs on every open and every edit pause, so long documents get no digit suggestion.
    for field, value in amounts if len(failing) >= 2 and len(amounts) <= 40 else ():
        for candidate in one_digit_changes(value):
            if not sums_fail(changed({field: candidate})):
                found.append((field, value, candidate, f'Did you mean {num(candidate)} instead of {num(value)}? Then every sum adds up.'))
                if len(found) > 1:
                    return None  # two different fixes both fit: the numbers can't tell which is right
    # Only "subtotal + tax + service - discount = total" fails: the tax or the total was misread. Each candidate
    # must make every sum pass. A printed rate keeps the one whose tax matches it; otherwise both are offered.
    net = line_net(doc)
    rate = doc.tax_rate if doc.tax_kind in ('vat', 'gst') else None
    if (not found and failing == {'total_math'} and doc.tax and doc.subtotal is not None and doc.total is not None
            # the tax looks included in the prices (CORD test 43): adding it on top would be wrong.
            # The subtotal may already hold it: 15,000 is 10/110 of 165,000
            and not doc.tax_included and not close(doc.subtotal, doc.total)
            and not included_share(doc.tax, doc.subtotal, net)
            and not (rate and abs(doc.tax - doc.subtotal * rate / (100 + rate)) <= CENT)
            # a total rounded to whole units (CORD test 51) gives no exact candidate
            and CENTS_PRINTED.search(doc.total_text or '') and doc.currency and doc.currency.upper() not in WHOLE_UNIT_CASH):
        rest = doc.subtotal + (doc.service_charge or 0) - abs(doc.discount or 0)
        options = [(f, v) for f, v in (('tax', doc.total - rest), ('total', rest + doc.tax))
                   if v * doc.total > 0 and v != getattr(doc, f) and not sums_fail(changed({f: v}))]  # a refund stays negative
        if doc.tax_rate is not None and doc.tax_kind:
            fits = [(f, v) for f, v in options if not any(i['check'] == 'tax_rate' for i in validate(changed({f: v})))]
            if len(fits) == 1:
                options = fits
        # A charge the reading missed (delivery, a tip; at least 1, never a few cents) looks the same as a total
        # misread too high: it is offered beside that total, never alone. Planted missed charges got 159 wrong
        # "Is the total" and 951 choices without the right answer.
        charge = (doc.service_charge or 0) + doc.total - rest - doc.tax
        if doc.total > 0 and 'total' in (f for f, _ in options) and charge - (doc.service_charge or 0) >= 1 and not sums_fail(changed({'service_charge': charge})):
            options.append(('service_charge', charge))
        change = lambda f, v: [{'field': f, 'from': None if getattr(doc, f) is None else str(getattr(doc, f)), 'to': str(v)}]
        if len(options) == 1:
            f, v = options[0]
            msg = 'Then the total adds up.' if f == 'tax' else 'Then every sum adds up.'
            return {'message': f'Is the {f} {num(v)}? {msg}', 'changes': change(f, v)}
        if options:
            message = {('tax', 'total'): 'The tax or the total was misread. Pick the one the photo shows.',
                       ('total', 'service_charge'): 'The total was misread, or a charge was not read. Pick the one the photo shows.',
                       ('tax', 'total', 'service_charge'): 'The tax or the total was misread, or a charge was not read. Pick the one the photo shows.'}
            label = {'tax': 'Tax', 'total': 'Total', 'service_charge': 'Other charge'}
            return {'message': message[tuple(f for f, _ in options)], 'changes': [],
                    'options': [{'label': f'{label[f]} {num(v - (doc.service_charge or 0) if f == "service_charge" else v)}',
                                 'changes': change(f, v)} for f, v in options]}
    if not found:
        return None
    field, value, candidate, message = found[0]
    return {'message': message, 'changes': [{'field': field, 'from': str(value), 'to': str(candidate)}]}
