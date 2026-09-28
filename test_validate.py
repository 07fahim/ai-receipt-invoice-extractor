from datetime import date
from decimal import Decimal as D

from schema import Document, Item
from validate import validate

TODAY = date(2026, 9, 28)


def checks(**kw):
    return [i['check'] for i in validate(Document(**kw), today=TODAY)]


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
# rounding: 0.1% tolerance (IDR tax rounding), but a 1% error is caught
assert checks(subtotal=D('46636'), tax=D('4664'), total=D('51300')) == []
assert checks(subtotal=D('46636'), tax=D('4664'), total=D('51800')) == ['total_math']
# missing inputs skip checks instead of failing them
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
print('ok')
