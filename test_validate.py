from datetime import date
from decimal import Decimal as D

from schema import Document, Item
from validate import apply_date_order, validate

TODAY = date(2026, 9, 28)


def checks(**kw):
    """Failed check names; items_missing is ignored here and tested on its own below."""
    return [i['check'] for i in validate(Document(**kw), today=TODAY) if i['check'] != 'items_missing']


good = dict(
    currency='USD', issue_date=date(2026, 9, 18), due_date=date(2026, 10, 18),
    subtotal=D('850.00'), tax=D('127.50'), discount=D('0'), total=D('977.50'),
    items=[Item(description='Cups', quantity=2, unit_price=D('350'), amount=D('700')),
           Item(description='Napkins', quantity=1, unit_price=D('150'), amount=D('150'))])

assert checks(**good) == []
assert checks(**{**good, 'total': None}) == ['total_present']
assert checks(**{**good, 'total': D('997.50')}) == ['total_math']
assert checks(**{**good, 'subtotal': D('800'), 'total': D('927.50')}) == ['items_sum']
assert checks(**{**good, 'items': [good['items'][0]]}) == ['items_sum']  # a dropped line item
assert checks(**{**good, 'items': [Item(quantity=3, unit_price=D('350'), amount=D('700')), good['items'][1]]}) == ['line_math']
assert checks(**{**good, 'issue_date': date(2027, 1, 1), 'due_date': None}) == ['date_future']
assert checks(**{**good, 'due_date': date(2026, 9, 1)}) == ['due_before_issue']
assert checks(**{**good, 'currency': 'RP'}) == ['currency_code']
assert checks(**{**good, 'currency': 'bdt'}) == []

# discount as negative or positive number, service charge counted
assert checks(**{**good, 'discount': D('-50'), 'total': D('927.50')}) == []
assert checks(**{**good, 'discount': D('50'), 'total': D('927.50')}) == []
assert checks(**{**good, 'service_charge': D('10'), 'total': D('987.50')}) == []
# the total may be cash-rounded (0.05%), line sums may not
assert checks(subtotal=D('334011'), total=D('334000')) == []
assert checks(subtotal=D('334011'), total=D('334500')) == ['total_math']
assert checks(subtotal=D('91000'), total=D('91000'), items=[Item(amount=D('91070'))]) == ['items_sum']
# ...but a total with cents is never cash-rounded: one misread cents digit is caught
assert checks(**{**good, 'total': D('977.55')}) == ['total_math'] and checks(**{**good, 'total': D('977.51')}) == []
# 5-cent cash rounding (CHF, AUD, CAD): 12.37 printed as 12.35 is fine, 12.30 is not
assert checks(subtotal=D('12.37'), total=D('12.35')) == [] and checks(subtotal=D('12.37'), total=D('12.30')) == ['total_math']
# missing inputs skip checks instead of failing them
assert [i['check'] for i in validate(Document(total=D('10')))] == ['items_missing']
assert [i['check'] for i in validate(Document())] == ['total_present']
assert checks(total=D('10')) == []
assert checks(total=D('10'), subtotal=D('10'), items=[Item(amount=None)]) == []
assert checks(total=D('10'), items=[Item(amount=None)]) == []
# line discounts reduce the items sum
assert checks(**{**good, 'items': [Item(amount=D('700'), discount=D('-100')), good['items'][1]], 'subtotal': D('750'), 'total': D('877.50')}) == []
# tax-inclusive: lines = subtotal + tax, or total = subtotal with tax already inside
assert checks(subtotal=D('22728'), tax=D('2272'), total=D('25000'), items=[Item(amount=D('25000'))]) == []
# total = subtotal while tax exists is flagged (it is also what "subtotal taken as total" looks like)
assert checks(subtotal=D('165000'), tax=D('15000'), total=D('165000')) == ['total_math']
# no subtotal: lines must add up to the total
assert checks(total=D('91000'), items=[Item(amount=D('17500')), Item(amount=D('46000')), Item(amount=D('27500'))]) == []
assert checks(total=D('91000'), items=[Item(amount=D('17500')), Item(amount=D('46000'))]) == ['items_total']
# printed dates: ambiguous day/month is flagged unless the vendor's date order is known
from validate import ambiguous, read_date
assert ambiguous('05/11/2021') and not ambiguous('09/18/2015') and not ambiguous('05/05/2021') and not ambiguous('2021-05-11')
assert read_date('05/11/2021', 'MDY') == date(2021, 5, 11) and read_date('05/11/21', 'DMY') == date(2021, 11, 5)
assert read_date('13/13/2021', 'MDY') is None and read_date(None, 'MDY') is None
amb = dict(total=D('10'), items=[Item(amount=D('10'))], issue_date=date(2021, 11, 5), issue_date_text='05/11/2021')
assert checks(**amb) == ['date_ambiguous']
fixed = validate(Document(**amb), today=TODAY, date_order='MDY')
assert fixed == []  # re-read as 11 May 2021, not flagged
assert apply_date_order(Document(**amb), 'MDY').issue_date == date(2021, 5, 11)

# printed total: thousands read as decimals ("22.000" -> 22) is flagged; the right reading and real cents are not
from validate import thousands_read_as_decimals as tr
small = lambda total, text, **kw: checks(total=D(total), total_text=text, items=[Item(amount=D(total))], **kw)
assert small('22', '22.000') == ['total_format'] and small('7', '·7,000') == ['total_format']
assert small('1250', 'Rp 1.250.000') == ['total_format'] and small('22000', '22.000') == []
assert small('7.61', '$7.61') == [] and small('1250', '1,250.00') == [] and small('22', None) == []
assert small('22', '22.000', currency='KWD') == []  # dinars really have 3 decimals
assert tr('TOTAL 22.000', D('22')) == '22.000' and tr('22.000', D('22000')) is None and tr('0.500', D('0.5')) is None
# "VAT included" (Bangladeshi supershops): subtotal = total and the VAT is inside the prices
incl = dict(subtotal=D('1150'), tax=D('150'), total=D('1150'), items=[Item(amount=D('1000')), Item(amount=D('150'))])
assert checks(**incl, tax_included=True) == [] and checks(**incl) == ['total_math'] and checks(**incl, tax_included=False) == ['total_math']
no_sub = {**incl, 'subtotal': None}
assert checks(**no_sub, tax_included=True) == [] and checks(**no_sub) == []  # unknown: either reading is accepted
assert checks(**no_sub, tax_included=False) == ['items_total']  # tax said to be on top, but the lines already reach the total
assert checks(**good, tax_included=True) == []  # tax added on top but marked included (Mushak 'incl.' column): numbers still agree

# not a receipt at all (menu, logo): one clear message instead of "No total found"; unknown counts as a document
assert [i['check'] for i in validate(Document(is_document=False))] == ['is_document']
assert checks(**good, is_document=True) == [] and checks(**good, is_document=None) == []

# several receipts in one photo go to review; one (or unknown) does not
assert checks(**good, document_count=2) == ['one_document'] and checks(**good, document_count=1) == []
msg = validate(Document(total=D('22'), total_text='22.000', items=[Item(amount=D('22'))]), today=TODAY)[0]['message']
assert msg == 'Total printed as 22.000: is it 22,000 rather than 22?', msg
print('ok')
