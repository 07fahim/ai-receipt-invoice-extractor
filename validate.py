"""Deterministic checks on an extracted Document. No AI: a failed check sends the document to review."""
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


def validate(doc: Document, today: date | None = None) -> list[dict]:
    """Return failed checks as {'check', 'fields', 'message'}. Empty list = passed.
    Checks with missing inputs are skipped, except a missing total."""
    today = today or date.today()
    issues = []

    def fail(check, fields, message):
        issues.append({'check': check, 'fields': fields, 'message': message})

    if doc.total is None:
        fail('total_present', ['total'], 'No total found')

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
        # no subtotal printed: the lines themselves must add up to the total
        net = sum(i.amount - abs(i.discount or 0) for i in doc.items)
        expected = net + tax + (doc.service_charge or 0) - abs(doc.discount or 0)
        if not (close(expected, doc.total, TOTAL_ROUNDING) or (tax and close(expected - tax, doc.total, TOTAL_ROUNDING))):
            fail('items_total', ['items', 'total'], f'Line items add up to {expected}, total is {doc.total}')

    for n, i in enumerate(doc.items):
        if None not in (i.quantity, i.unit_price, i.amount) and not close(i.quantity * i.unit_price, i.amount):
            fail('line_math', [f'items[{n}]'], f'{i.quantity} x {i.unit_price} = {i.quantity * i.unit_price}, line amount is {i.amount}')

    if doc.issue_date is not None and doc.issue_date > today:  # due dates are allowed in the future
        fail('date_future', ['issue_date'], f'Issue date {doc.issue_date} is in the future')
    if doc.issue_date and doc.due_date and doc.due_date < doc.issue_date:
        fail('due_before_issue', ['issue_date', 'due_date'], 'Due date is before issue date')

    if doc.currency is not None and doc.currency.upper() not in CURRENCIES:
        fail('currency_code', ['currency'], f'"{doc.currency}" is not an ISO 4217 currency code')

    return issues
