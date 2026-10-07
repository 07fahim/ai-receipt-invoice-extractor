from datetime import date
from decimal import Decimal as D

from schema import Document, Item
from validate import apply_date_order, validate

TODAY = date(2026, 9, 28)


def checks(**kw):
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
assert checks(**{**good, 'issue_date': date(2026, 9, 29), 'due_date': None}) == []  # tomorrow in UTC can be today in Dhaka
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
assert apply_date_order(Document(**{**amb, 'issue_date': date(2021, 12, 25)}), 'MDY').issue_date == date(2021, 12, 25)  # typed by the user: kept

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
assert checks(**incl, tax_included=True) == [] and checks(**incl) == [] and checks(**incl, tax_included=False) == []  # 150 is exactly the 15% inside 1150
odd = {**incl, 'tax': D('140')}  # not the share of any known rate: only the model's word counts
assert checks(**odd, tax_included=True) == [] and checks(**odd) == ['total_math'] and checks(**odd, tax_included=False) == ['total_math']
no_sub = {**incl, 'subtotal': None}
assert checks(**no_sub, tax_included=True) == [] and checks(**no_sub) == []  # unknown: either reading is accepted
assert checks(**no_sub, tax_included=False) == []  # said to be on top, but 150 is exactly the 15% inside 1150
assert checks(**{**no_sub, 'tax': D('100')}, tax_included=False) == ['items_total']  # on top, lines already reach the total
assert checks(**good, tax_included=True) == []  # tax added on top but marked included (Mushak 'incl.' column): numbers still agree

# not a receipt at all (menu, logo): one clear message instead of "No total found"; unknown counts as a document
assert [i['check'] for i in validate(Document(is_document=False))] == ['is_document']
assert checks(**good, is_document=True) == [] and checks(**good, is_document=None) == []

# several receipts in one photo go to review; one (or unknown) does not
assert checks(**good, document_count=2) == ['one_document'] and checks(**good, document_count=1) == []
# Bangladeshi receipts (data/sample images): weighed items, rounding to whole taka, item discounts listed apart,
# VAT included that the model called "added on top"
assert checks(total=D('41.36'), items=[Item(quantity=D('1.03'), unit_price=D('40'), amount=D('41.36'))]) == []
assert checks(total=D('47.36'), items=[Item(quantity=D('1.03'), unit_price=D('40'), amount=D('47.36'))]) == ['line_math']
assert checks(total=D('10.6'), items=[Item(quantity=3, unit_price=D('3.5'), amount=D('10.6'))]) == ['line_math']
assert checks(subtotal=D('434.80'), discount=D('30.44'), total=D('404'),
              items=[Item(amount=D('139.80'), discount=D('9.79')), Item(amount=D('295'), discount=D('20.65'))]) == []
assert checks(subtotal=D('434.80'), discount=D('30.44'), total=D('403')) == ['total_math']
star = dict(subtotal=D('830'), total=D('830'), items=[Item(amount=D('790')), Item(amount=D('40'))], tax_included=False)
assert checks(**star, tax=D('39.52')) == [] and checks(**star, tax=D('41.50')) == ['total_math']
# ...but never without lines that reach the total: 10% on top with the subtotal read as the total looks the same
assert checks(subtotal=D('165000'), tax=D('15000'), total=D('165000'), items=[Item(amount=D('150000'))]) == ['items_sum', 'total_math']
# a discount recorded on the item and again on the receipt, printed before SUBTTL (CORD test 33): not subtracted twice
itm = dict(subtotal=D('117500'), discount=D('67000'), items=[Item(amount=D('50500')), Item(amount=D('67000')), Item(amount=D('67000'), discount=D('67000'))])
assert checks(**itm, total=D('117500')) == [] and checks(**itm, total=D('50500')) == ['total_math']
assert checks(total=D('11700'), discount=D('7800'), items=[Item(amount=D('19500'), discount=D('7800'))]) == []
# suggestions for the review screen: one misread digit that breaks two checks, or thousands read as decimals
from validate import suggest
memo = dict(subtotal=D('1230'), total=D('1230'), items=[Item(quantity=2, unit_price=D('140'), amount=D('280')),
            Item(quantity=2, unit_price=D('120'), amount=D('280')), Item(quantity=1, unit_price=D('710'), amount=D('710'))])
assert suggest(Document(**memo))['changes'] == [{'field': 'items[1].amount', 'from': '280', 'to': '240'}]
assert suggest(Document(**{**memo, 'total': D('1270'), 'subtotal': D('1270')})) is None  # nothing fails
assert suggest(Document(subtotal=D('100'), total=D('180'))) is None  # one failed check: never guess
assert suggest(Document(subtotal=D('21'), total=D('21'), items=[Item(amount=D('10')), Item(amount=D('10'))])) is None  # items_sum alone: one check, no guess
k = suggest(Document(total=D('22'), total_text='22.000', subtotal=D('22'), items=[Item(amount=D('22'))]))
assert {c['field']: c['to'] for c in k['changes']} == {'subtotal': '22000', 'total': '22000', 'items[0].amount': '22000'}, k
# a weighed item read as quantity 1 ("Beef Ribs 1.89 lb @ 19.50 = 36.86")
ribs = dict(subtotal=D('42.86'), total=D('42.86'), items=[Item(description='Beef Ribs', quantity=1, unit_price=D('19.50'), amount=D('36.86')),
            Item(description='Bread', quantity=2, unit_price=D('3'), amount=D('6'))])
s = suggest(Document(**ribs))
assert s == {'message': 'Beef Ribs: is the quantity 1.89? Then the line adds up.',
             'changes': [{'field': 'items[0].quantity', 'from': '1', 'to': '1.89'}]}, s
assert checks(**{**ribs, 'items': [ribs['items'][0].model_copy(update={'quantity': D('1.89')}), ribs['items'][1]]}) == []
s = suggest(Document(total=D('7.50'), items=[Item(quantity=1, unit_price=D('2.50'), amount=D('7.50'))]))
assert s['changes'] == [{'field': 'items[0].quantity', 'from': '1', 'to': '3'}] and s['message'].startswith('Line 1:'), s
assert suggest(Document(total=D('10'), items=[Item(quantity=1, unit_price=D('7'), amount=D('10'))])) is None  # 1.428 and 1.429 both fit
two = [Item(quantity=1, unit_price=D('2.50'), amount=D('7.50')), Item(quantity=1, unit_price=D('2'), amount=D('4'))]
assert suggest(Document(total=D('11.50'), items=two)) is None  # two lines fail
assert suggest(Document(**memo)) == {'message': 'Did you mean 240 instead of 280? Then every sum adds up.',
                                     'changes': [{'field': 'items[1].amount', 'from': '280', 'to': '240'}]}  # amount wrong, not 2.333
assert suggest(Document(**{**ribs, 'total': D('50')})) is None  # the total would still be off
assert suggest(Document(total=D('0.58'), items=[Item(quantity=D('1.76'), unit_price=D('0.99'), amount=D('0.58'))])) is None  # 0.99/3 lb: the price is wrong
# a total printed with cents gets no whole-unit rounding room, except where cash is rounded to whole units
cents = dict(subtotal=D('1199.60'), total=D('1200.00'), total_text='1,200.00', items=[Item(amount=D('1199.60'))])
assert checks(**cents, currency='USD') == ['total_math'] and checks(**cents) == []  # unknown currency: lenient
assert checks(**cents, currency='BDT') == [] and checks(**{**cents, 'total_text': '1,200'}, currency='USD') == []
# oversized input is refused before any check runs
import pydantic
for bad in ({'items': [{}] * 201}, {'total': '1e100000'}):
    try:
        Document(**bad)
        raise AssertionError(bad)
    except pydantic.ValidationError:
        pass
msg = validate(Document(total=D('22'), total_text='22.000', items=[Item(amount=D('22'))]), today=TODAY)[0]['message']
assert msg == 'The total is printed as 22.000. Is it 22,000?', msg
from validate import num
assert [num(D(x)) for x in ('1270.0', '0.6', '0.63', '1.005', '9983196.70')] == ['1,270', '0.60', '0.63', '1.005', '9,983,196.70']

from validate import review
def found(**kw):
    return {i['check']: i['message'] for i in validate(Document(**kw), today=TODAY)}
mehedi = dict(subtotal=D('896'), discount=D('44.80'), tax=D('120'), total=D('971.20'), tax_rate=15, tax_kind='vat',
              seller_tax_id='0012-3456-7890', items=[Item(amount=D('896'))])
assert found(**mehedi) == {'tax_rate': 'VAT 15% of 851.20 is 127.68. The document says 120.'}, found(**mehedi)
assert found(**{**mehedi, 'tax': D('127.68'), 'total': D('978.88')}) == {}
assert found(**{**mehedi, 'tax': D('111.03'), 'total': D('962.23')}) == {}  # VAT included in the prices
greenleaf = dict(subtotal=D('16'), discount=D('1.60'), tax=D('3.20'), total=D('17.60'), tax_rate=20, tax_kind='vat',
                 seller_tax_id='GB123456782', items=[Item(amount=D('16'))])
assert found(**greenleaf) == {'tax_rate': 'VAT 20% of 14.40 is 2.88. The document says 3.20.'}  # VAT before the discount
restaurant = dict(subtotal=D('1000'), service_charge=D('100'), tax=D('165'), total=D('1265'), tax_rate=15, tax_kind='vat',
                  seller_tax_id='004567891-0102', items=[Item(amount=D('1000'))])
assert found(**restaurant) == {}  # VAT on subtotal + service charge
gst_halves = dict(subtotal=D('1000'), tax=D('50'), total=D('1050'), tax_rate=5, tax_kind='gst',
                  seller_tax_id='07AAHCA1234F1Z5', items=[Item(amount=D('1000'))])
assert found(**gst_halves) == {}
maple = dict(subtotal=D('80.44'), discount=D('8.04'), tax=D('8.55'), total=D('80.95'), tax_rate=D('8.5'), tax_kind='sales_tax',
             items=[Item(amount=D('80.44'))])
assert found(**maple) == {'tax_rate': 'Tax 8.5% of 80.44 is at most 6.84. The document says 8.55.'}
target_tax = dict(subtotal=D('26.85'), tax=D('1.20'), total=D('28.05'), tax_rate=7, tax_kind='sales_tax', items=[Item(amount=D('26.85'))])
assert found(**target_tax) == {}  # less sales tax than the rate: some items can be exempt
walmart = dict(subtotal=D('29.18'), tax=D('2.86'), total=D('32.04'), tax_rate=0, tax_kind='sales_tax', items=[Item(amount=D('29.18'))])
assert found(**walmart) == {'tax_rate': 'Tax 0% of 29.18 is at most 0.00. The document says 2.86.'}
target_disc = dict(subtotal=D('26.85'), discount=D('3.49'), tax=D('1.64'), total=D('25.00'), discount_rate=10, items=[Item(amount=D('26.85'))])
assert found(**target_disc) == {'discount_rate': '10% of 26.85 is 2.69. The discount is 3.49.'}
assert found(**{**target_disc, 'discount': D('2.69'), 'total': D('25.80')}) == {}
assert found(**{**mehedi, 'tax_rate': None}) == {} and found(**{**mehedi, 'tax_kind': None}) == {}  # nothing printed: skipped
assert review([{'check': 'a', 'level': 'note'}, {'check': 'b'}]) == [{'check': 'b'}]
print('ok')
