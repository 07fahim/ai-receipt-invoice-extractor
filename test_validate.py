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
assert checks(subtotal=D('12.37'), total=D('12.35'), currency='CHF') == []
assert checks(**{**good, 'total': D('977.55')}) == ['total_math']  # dollars are not cash-rounded: 977.50 for 977.52 is caught
assert checks(**{**good, 'tax': D('127.52')}) == ['total_math']
# taka and rupees are cut or rounded to whole units, never by hundreds (977,500 read as 977,900 was let through by 0.05%)
taka = dict(subtotal=D('977500'), total=D('977500'), currency='BDT', items=[Item(amount=D('977500'))])
assert checks(**{**taka, 'total': D('977900')}) == ['total_math'] and checks(**{**taka, 'subtotal': D('977500.70'), 'items': [Item(amount=D('977500.70'))]}) == []
assert checks(**{**taka, 'currency': 'IDR', 'total': D('977900')}) == []  # rupiah: rounded to hundreds
small_taka = lambda sub, total: checks(subtotal=D(sub), total=D(total), currency='bdt', items=[Item(amount=D(sub))])
assert small_taka('403.60', '404') == [] and small_taka('404.90', '404') == []  # rounded up, or cut
assert small_taka('403.01', '404') == ['total_math'] and small_taka('405.00', '404') == ['total_math']
assert checks(subtotal=D('12.37'), total=D('12.35'), currency='chf') == []
# no total_text: a dollar total gets no whole-unit room
assert checks(subtotal=D('978.40'), total=D('978'), currency='USD') == ['total_math']
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
odd = {**incl, 'tax': D('140')}  # 140 inside 1150 is 13.9%, no VAT rate: the model's word is not enough
assert checks(**odd, tax_included=True) == ['total_math'] and checks(**odd) == ['total_math'] and checks(**odd, tax_included=False) == ['total_math']
# tax added on top, the subtotal read as the total and marked included: 10 of 100 is no rate's share (9.09 would be 10%)
on_top = dict(subtotal=D('100'), tax=D('10'), total=D('100'), currency='USD', items=[Item(amount=D('100'))])
assert checks(**on_top, tax_included=True) == ['total_math'] and checks(**{**on_top, 'tax': D('16.67')}, tax_included=True) == []
# where receipts mix rates, any share up to the top rate passes; standard rate on top lands above it
mixed = lambda cur, tax, total, tax_id=None: checks(subtotal=D(total), tax=D(tax), total=D(total), currency=cur, tax_included=True,
                                                    seller_tax_id=tax_id, items=[Item(amount=D(total))])
assert mixed('EUR', '4.15', '29.15') == [] and mixed('EUR', '2.66', '22.66') == [] and mixed('JPY', '188', '2188') == []  # 7+19%, 5.5+20%, 8+10%
assert mixed('CHF', '4.05', '54.05') == [] and mixed('SEK', '25', '125') == [] and mixed('GBP', '10', '100') == []  # 8.1%, 25%, 0+20%
assert mixed('GBP', '20', '100') == ['total_math'] and mixed('EUR', '19', '100', 'DE123456789') == ['total_math']  # 20%, 19% on top
assert mixed('EUR', '20.32', '100', 'FI12345678') == [] and mixed('EUR', '20.32', '100') == []  # Finland 25.5%
assert mixed('EUR', '10', '100') == ['total_math'] and mixed('JPY', '80', '1000') == ['total_math']  # 10%, 8% on top
assert mixed('EUR', '25', '100', 'FR12345678901') == ['total_math']  # 20% on top looks like 25% included: not a French rate
# invoices add the tax on top: two rates on top (Italy 100 at 10% + 100 at 22%, subtotal 200 read as the total) is no mix
inv = lambda tax, total, tax_id=None, doc_type='invoice': checks(doc_type=doc_type, subtotal=D(total), tax=D(tax), total=D(total),
                                                             currency='EUR', tax_included=True, seller_tax_id=tax_id, items=[Item(amount=D(total))])
assert inv('32', '200', 'IT1') == ['total_math'] and inv('32', '200', 'IT1', 'receipt') == []
assert inv('5.21', '100') == [] and inv('5.21', '100', 'FR1') == []  # one rate, 5.5% included (France)
assert inv('20', '100', 'FR1') == ['total_math'] and inv('20.32', '100', 'FI1') == []  # 20% on top; Finland 25.5% included
assert mixed('EUR', '4.15', '29.15', 'DE1') == []  # a German receipt mixing 7% and 19%, unchanged
assert inv('20.32', '100') == [] and inv('5.21', '100', 'SIRET 123') == []  # 25.5% without a prefix; a label is no country
assert inv('11.89', '100', 'IE1') == [] and checks(doc_type='invoice', subtotal=D('125'), tax=D('25'), total=D('125'), currency='SEK',
                                                   tax_included=True, items=[Item(amount=D('125'))]) == []  # IE 13.5%, SE 25%
on_top2 = lambda cur, tax, tax_id=None: checks(doc_type='invoice', subtotal=D('200'), tax=D(tax), total=D('200'), currency=cur,
                                               tax_included=True, seller_tax_id=tax_id, items=[Item(amount=D('200'))])
assert on_top2('EUR', '26', 'DE1') == on_top2('JPY', '18') == on_top2('GBP', '20') == ['total_math']  # 7+19, 8+10, 0+20 on top
# the share of the subtotal also counts: a tip without VAT added after it (WildReceipt test 270, ZAR 14%)
assert checks(subtotal=D('318'), tax=D('39.05'), service_charge=D('32'), total=D('350'), tax_included=True, items=[Item(amount=D('318'))]) == []
no_sub = {**incl, 'subtotal': None}
assert checks(**no_sub, tax_included=True) == [] and checks(**no_sub) == []  # unknown: either reading is accepted
assert checks(**no_sub, tax_included=False) == []  # said to be on top, but 150 is exactly the 15% inside 1150
assert checks(**{**no_sub, 'tax': D('100')}, tax_included=False) == ['items_total']  # on top, lines already reach the total
assert checks(**good, tax_included=True) == []  # tax added on top but marked included (Mushak 'incl.' column): numbers still agree

# the VAT summary rows: with rows, the included decision and the row checks use them
from schema import VatLine
row = lambda rate, net, tax, gross=None: VatLine(rate=D(rate), net=D(net), tax=D(tax), gross=None if gross is None else D(gross))
two = [row('7', '100.00', '7.00', '107.00'), row('19', '50.00', '9.50', '59.50')]
base = dict(currency='EUR', subtotal=D('166.50'), tax=D('16.50'), total=D('166.50'), tax_included=True, vat_lines=two,
            items=[Item(amount=D('107.00')), Item(amount=D('59.50'))])
assert checks(**base) == []  # a genuine mixed receipt: the total is the rows' gross
assert checks(**{**base, 'vat_lines': [row('7', '100.00', '8.00', '108.00'), two[1]], 'tax': D('17.50'),
                 'subtotal': D('167.50'), 'total': D('167.50'), 'items': [Item(amount=D('108.00')), Item(amount=D('59.50'))]}) == ['vat_row']
assert checks(**{**base, 'tax': D('16.00')}) == ['vat_rows_tax']  # total still equals the rows' gross
# tax on top, subtotal read as the total, marked included: the rows' gross is 166.50, the total read 150.00
assert checks(**{**base, 'subtotal': D('150.00'), 'total': D('150.00'), 'items': [Item(amount=D('100')), Item(amount=D('50'))]}) == ['total_math']
# a small total: 0.75 is 15% of 5.00 added on top; the row's gross is 5.75, not the 5.00 read as the total
assert checks(currency='GBP', subtotal=D('5.00'), tax=D('0.75'), total=D('5.00'), tax_included=True, items=[Item(amount=D('5.00'))],
              vat_lines=[row('15', '5.00', '0.75', '5.75')]) == ['total_math']
# real receipts print zero rows beside a real one (a French receipt: 5.5% and 20% at 0.00 beside a real 10% row)
zero = dict(currency='EUR', subtotal=D('50.00'), tax=D('5.00'), total=D('55.00'), tax_included=False,
            items=[Item(amount=D('55.00'))],
            vat_lines=[row('5.5', '0.00', '0.00', '0.00'), row('20', '0.00', '0.00', '0.00'), row('10', '50.00', '5.00', '55.00')])
assert checks(**zero) == []
# currencies with no cents: a whole-unit row gap gets the same room as doc.tax, not a flat cent-per-item room
jpy = dict(currency='JPY', subtotal=D('1234'), tax=D('98'), total=D('1332'), tax_included=True,
           items=[Item(amount=D('1332'))], vat_lines=[row('8', '1234', '98', '1332')])
assert checks(**jpy) == []  # 8% of 1234 is 98.72, printed whole as 98
# unknown currency: a whole-number row tax still gets the room; a known cash currency always does
idr1 = dict(currency=None, subtotal=D('25000'), tax=D('2500'), total=D('27500'), tax_included=False,
            items=[Item(amount=D('27500'))], vat_lines=[row('10', '25000', '2500')])
assert checks(**idr1) == []
idr2 = dict(currency='IDR', subtotal=D('25000'), tax=D('2502'), total=D('27502'), tax_included=False,
            items=[Item(amount=D('27502'))], vat_lines=[row('10', '25000', '2502')])
assert checks(**idr2) == ['vat_row']  # 2 units off, still outside the 1-unit room

# a partly read row (net missing) must not cause false flags: the sum check counts every row with tax set,
# and "VAT included" falls back to the old term since not every row is complete
f1 = dict(currency='EUR', subtotal=D('166.50'), tax=D('16.50'), total=D('166.50'), tax_included=True,
          items=[Item(amount=D('107.00')), Item(amount=D('59.50'))],
          vat_lines=[row('7', '100.00', '7.00', '107.00'), VatLine(rate=D('19'), net=None, tax=D('9.50'), gross=D('59.50'))])
assert checks(**f1) == []

# a misread row (gross read into net) must not also fire total_math: the rows don't decide "included" unless
# every row is complete and passes its own arithmetic, so the old term is used instead
f2 = dict(currency='EUR', subtotal=D('166.50'), tax=D('16.50'), total=D('166.50'), tax_included=True,
          items=[Item(amount=D('107.00')), Item(amount=D('59.50'))],
          vat_lines=[row('7', '107.00', '7.00'), row('19', '59.50', '9.50')])
assert checks(**f2) == ['vat_row', 'vat_row']

# a row whose gross doesn't match net + tax (but whose own rate arithmetic is fine) gets its own message
f3 = dict(currency='EUR', subtotal=D('100.00'), tax=D('7.00'), total=D('107.00'),
          items=[Item(amount=D('107.00'))], vat_lines=[row('7', '100.00', '7.00', '108.00')])
f3_issues = [i for i in validate(Document(**f3), today=TODAY) if i['check'] != 'items_missing']
assert [i['check'] for i in f3_issues] == ['vat_row'], f3_issues
assert f3_issues[0]['message'] == 'The 7% VAT row: 100 + 7 is 107. It says 108.', f3_issues
assert f3_issues[0]['fields'] == ['tax'], f3_issues

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
# Star Hotel read with a line that has no amount: the printed 5% is enough to show the VAT is inside the 830
hotel = dict(subtotal=D('830'), tax=D('39.52'), total=D('830'), tax_rate=5, tax_kind='vat', tax_included=False,
             seller_tax_id='000107602-0201', items=[Item(amount=D('790')), Item(amount=D('40')), Item(description='Water')])
assert checks(**hotel) == []
assert checks(**{**hotel, 'tax_rate': None}) == ['total_math'] and checks(**{**hotel, 'tax': D('41.50')}) == ['total_math']
# same shape but sales tax: a subtotal misread as the total must not pass just because the printed rate's
# included share happens to match (that proof is VAT/GST only, see I-1)
hotel_sales = dict(subtotal=D('108.50'), tax=D('8.50'), total=D('108.50'), tax_rate=D('8.5'), tax_kind='sales_tax',
                    tax_included=False, items=[Item(amount=D('60')), Item(amount=D('40')), Item(description='Water')])
assert 'total_math' in checks(**hotel_sales), checks(**hotel_sales)
assert checks(**hotel) == []  # hotel VAT case still passes
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
# CORD test 0: "60.000" read as 60. Other sums fail before and after x1000, so x1000 is offered when it adds no new failure
cord0 = {'currency': 'IDR', 'subtotal': D('60.0'), 'discount': D('60.0'), 'tax': D('5.455'), 'total': D('60.0'),
         'total_text': '60.000', 'tax_kind': 'vat',
         'items': [Item(description='TICKET CP', quantity=D(2), unit_price=D('60.0'), amount=D('60.0'))]}
s = suggest(Document(**cord0))
assert s and 'The total would be 60,000' in s['message'], s
k = suggest(Document(total=D('22'), total_text='22.000', subtotal=D('22'), items=[Item(amount=D('22'))]))
assert {c['field']: c['to'] for c in k['changes']} == {'subtotal': '22000', 'total': '22000', 'items[0].amount': '22000'}, k
# a weighed item read as quantity 1 ("Beef Ribs 1.89 lb @ 19.50 = 36.86")
ribs = dict(subtotal=D('42.86'), total=D('42.86'), items=[Item(description='Beef Ribs', quantity=1, unit_price=D('19.50'), amount=D('36.86')),
            Item(description='Bread', quantity=2, unit_price=D('3'), amount=D('6'))])
s = suggest(Document(**ribs))
assert s == {'message': 'Beef Ribs: is the quantity 1.89? Then the line adds up.',
             'changes': [{'field': 'items[0].quantity', 'from': '1', 'to': '1.89'}]}, s
assert checks(**{**ribs, 'items': [ribs['items'][0].model_copy(update={'quantity': D('1.89')}), ribs['items'][1]]}) == []
s = suggest(Document(total=D('9.00'), items=[Item(quantity=1, unit_price=D('2.25'), amount=D('9.00'))]))
assert s['changes'] == [{'field': 'items[0].quantity', 'from': '1', 'to': '4'}] and s['message'].startswith('Line 1:'), s
# one digit of the price fits too (2.50 for 7.50; 4 x 125 for 4 x 185): no guess
assert suggest(Document(total=D('7.50'), items=[Item(quantity=1, unit_price=D('2.50'), amount=D('7.50'))])) is None
assert suggest(Document(total=D('740'), items=[Item(quantity=4, unit_price=D('125'), amount=D('740'))])) is None
assert suggest(Document(total=D('10'), items=[Item(quantity=1, unit_price=D('7'), amount=D('10'))])) is None  # 1.428 and 1.429 both fit
two = [Item(quantity=1, unit_price=D('2.50'), amount=D('7.50')), Item(quantity=1, unit_price=D('2'), amount=D('4'))]
assert suggest(Document(total=D('11.50'), items=two)) is None  # two lines fail
assert suggest(Document(**memo)) == {'message': 'Did you mean 240 instead of 280? Then every sum adds up.',
                                     'changes': [{'field': 'items[1].amount', 'from': '280', 'to': '240'}]}  # amount wrong, not 2.333
assert suggest(Document(**{**ribs, 'total': D('50')})) is None  # the total would still be off
assert suggest(Document(total=D('0.58'), items=[Item(quantity=D('1.76'), unit_price=D('0.99'), amount=D('0.58'))])) is None  # 0.99/3 lb: the price is wrong
# one sum fails (subtotal + tax = total): the tax or the total was misread
lines = [Item(description='x', quantity=D(1), unit_price=D(a), amount=D(a)) for a in ('10', '20', '3')]
both = suggest(Document(currency='USD', subtotal=D('33.00'), tax=D('8.30'), total=D('36.30'), total_text='36.30', items=lines))
assert both['changes'] == [] and both['message'] == 'The tax or the total was misread. Pick the one the photo shows.', both
assert [(o['label'], o['changes']) for o in both['options']] == [
    ('Tax 3.30', [{'field': 'tax', 'from': '8.30', 'to': '3.30'}]),
    ('Total 41.30', [{'field': 'total', 'from': '36.30', 'to': '41.30'}])], both
big = [Item(description='x', quantity=D(1), unit_price=D(a), amount=D(a)) for a in ('1000.00', '200.00')]
labels = suggest(Document(currency='GBP', subtotal=D('1200.00'), tax=D('880.50'), total=D('1380.50'), total_text='1,380.50', items=big))
assert [o['label'] for o in labels['options']] == ['Tax 180.50', 'Total 2,080.50'], labels  # thousands get commas
# a printed rate decides: 10% of 33 is 3.30, so the tax is the misread
one = suggest(Document(currency='USD', subtotal=D('33.00'), tax=D('8.30'), total=D('36.30'), total_text='36.30', tax_rate=D(10), tax_kind='vat', items=lines))
assert one == {'message': 'Is the tax 3.30? Then the total adds up.', 'changes': [{'field': 'tax', 'from': '8.30', 'to': '3.30'}]}, one
# the tax matches its rate, so the total is the misread, or a 50.00 charge (delivery, a tip) was not read
two = suggest(Document(currency='USD', subtotal=D('33.00'), tax=D('3.30'), total=D('86.30'), total_text='86.30', tax_rate=D(10), tax_kind='vat', items=lines))
assert two['message'] == 'The total was misread, or a charge was not read. Pick the one the photo shows.' and [o['changes'] for o in two['options']] == [
    [{'field': 'total', 'from': '86.30', 'to': '36.30'}], [{'field': 'service_charge', 'from': None, 'to': '50.00'}]], two
# a total below its parts can't hold a missed charge: one answer
one = suggest(Document(currency='USD', subtotal=D('33.00'), tax=D('3.30'), total=D('26.30'), total_text='26.30', tax_rate=D(10), tax_kind='vat', items=lines))
assert one == {'message': 'Is the total 36.30? Then every sum adds up.', 'changes': [{'field': 'total', 'from': '26.30', 'to': '36.30'}]}, one
three = suggest(Document(currency='USD', subtotal=D('33.00'), tax=D('3.30'), total=D('41.30'), total_text='41.30', items=lines))
assert [o['label'] for o in three['options']] == ['Tax 8.30', 'Total 36.30', 'Other charge 5'], three
# a service charge already read: the label gives the missed amount, the change the new service charge
svc = suggest(Document(currency='USD', subtotal=D('33.00'), tax=D('3.30'), service_charge=D('2.00'), total=D('43.30'), total_text='43.30', items=lines))
assert svc['options'][-1] == {'label': 'Other charge 5', 'changes': [{'field': 'service_charge', 'from': '2.00', 'to': '7.00'}]}, svc
# a refund: no option flips the sign of the tax or the total
refund = suggest(Document(currency='USD', subtotal=D('-33.00'), tax=D('-3.30'), total=D('-26.30'), total_text='-26.30', items=[Item(amount=D('-33.00'))]))
assert refund is None or all(D(c['to']) < 0 for o in refund.get('options') or [refund] for c in o['changes']), refund
# no guess when the tax is inside the prices (subtotal = total) or the total is printed in whole units (rounded)
assert suggest(Document(currency='USD', subtotal=D('33.00'), tax=D('8.00'), total=D('33.00'), total_text='33.00', items=lines)) is None
assert suggest(Document(currency='USD', subtotal=D('33.00'), tax=D('8.30'), total=D('36.30'), total_text='36', items=lines)) is None
# the tax is the share already inside the subtotal (CORD test 43: 15,000 is 10/110 of 165,000), the total misread
assert suggest(Document(currency='USD', subtotal=D('165000.00'), tax=D('15000.00'), total=D('65000.00'), total_text='65000.00',
                        items=[Item(amount=D('100000.00')), Item(amount=D('65000.00'))])) is None
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
mehedi = dict(currency='BDT', subtotal=D('896'), discount=D('44.80'), tax=D('120'), total=D('971.20'), tax_rate=15, tax_kind='vat',
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
gst_halves = dict(currency='INR', subtotal=D('1000'), tax=D('50'), total=D('1050'), tax_rate=5, tax_kind='gst',
                  seller_tax_id='07AAHCA1234F1Z5', items=[Item(amount=D('1000'))])
assert found(**gst_halves) == {}
maple = dict(subtotal=D('80.44'), discount=D('8.04'), tax=D('8.55'), total=D('80.95'), tax_rate=D('8.5'), tax_kind='sales_tax',
             items=[Item(amount=D('80.44'))])
assert found(**maple) == {'tax_rate': 'Tax 8.5% of 80.44 is at most 6.84. The document says 8.55.'}
target_tax = dict(subtotal=D('26.85'), tax=D('1.20'), total=D('28.05'), tax_rate=7, tax_kind='sales_tax', items=[Item(amount=D('26.85'))])
assert found(**target_tax) == {}  # less sales tax than the rate: some items can be exempt
walmart = dict(subtotal=D('29.18'), tax=D('2.86'), total=D('32.04'), tax_rate=0, tax_kind='sales_tax', items=[Item(amount=D('29.18'))])
assert found(**walmart) == {'tax_rate': 'Tax 0% of 29.18 is at most 0.00. The document says 2.86.'}
# the ceiling is subtotal + service charge: the message must print that sum, not the subtotal alone (M-2)
service_tax = dict(subtotal=D('100'), service_charge=D('18'), tax=D('13'), total=D('131'), tax_rate=10, tax_kind='sales_tax',
                    items=[Item(amount=D('100'))])
assert found(**service_tax) == {'tax_rate': 'Tax 10% of 118 is at most 11.80. The document says 13.'}, found(**service_tax)
target_disc = dict(subtotal=D('26.85'), discount=D('3.49'), tax=D('1.64'), total=D('25.00'), discount_rate=10, items=[Item(amount=D('26.85'))])
assert found(**target_disc) == {'discount_rate': '10% of 26.85 is 2.69. The discount is 3.49.'}
assert found(**{**target_disc, 'discount': D('2.69'), 'total': D('25.80')}) == {}
assert found(**{**mehedi, 'tax_rate': None}) == {} and found(**{**mehedi, 'tax_kind': None}) == {}  # nothing printed: skipped
# a whole-unit tax can be truncated instead of rounded (CORD 90: 10% of 26,818 = 2,681.80, printed 2,681)
cord90 = dict(subtotal=D('26818'), tax=D('2681'), total=D('29499'), tax_rate=10, tax_kind='vat',
              seller_tax_id='01.234.567.8-901.000', items=[Item(amount=D('26818'))])
assert found(**cord90) == {}
assert found(**{**cord90, 'tax': D('2679'), 'total': D('29497')}) == {
    'tax_rate': 'VAT 10% of 26,818 is 2,681.80. The document says 2,679.'}
# CORD test 33: discount recorded on the item and again on SUBTTL, so the subtotal already has it taken off;
# the tax_rate base must not subtract it a second time (the base still fails: the shop taxed the pre-discount amount)
cord33 = dict(currency='IDR', subtotal=D('117500'), discount=D('67000'), tax=D('19557'), tax_included=False,
              service_charge=D('11070'), total=D('148127'), tax_rate=D('10'), tax_kind='vat', discount_rate=D('100'),
              items=[Item(description='GRILLED BABY POTATO (R', quantity=D('1'), unit_price=D('50500'), amount=D('50500')),
                     Item(description='HOT TUNA', quantity=D('1'), unit_price=D('67000'), amount=D('67000')),
                     Item(description='HOT TUNA', quantity=D('1'), unit_price=D('67000'), amount=D('67000'), discount=D('67000'))])
assert found(**cord33) == {'tax_rate': 'VAT 10% of 117,500 is 11,750. The document says 19,557.'}, found(**cord33)
# no VAT number: Indonesian rupiah receipts tax a local restaurant tax, no VAT/GST number applies there
assert review([{'check': 'a', 'level': 'note'}, {'check': 'b'}]) == [{'check': 'b'}]

from validate import gstin_valid, uk_vat_valid
assert gstin_valid('07AAHCA1234F1Z5') and not gstin_valid('07AAHCA1234F1Z6') and not gstin_valid('99AAHCA1234F1Z5')
# 1234567: weights 8..2 give 112; 112 + 82 = 194 = 2 x 97 (old scheme); 112 + 27 + 55 = 194 (new scheme)
assert uk_vat_valid('123456782') and uk_vat_valid('123456727') and not uk_vat_valid('123456789')
from validate import tax_id_problem
# without GB on a pound receipt (WildReceipt 349 and 10 print '191 2478 96' and '142 440 545'); other currencies unchecked
assert tax_id_problem('191 2478 96', 'GBP') is None and tax_id_problem('142 440 545', 'GBP') is None
assert tax_id_problem('123 4567 89', 'GBP') and tax_id_problem('123 4567 89', 'USD') is None
assert found(**{**greenleaf, 'tax': D('2.88'), 'total': D('17.28'), 'seller_tax_id': 'GB123 4567 89'}) == \
    {'tax_id_invalid': 'GB123 4567 89 is not a valid UK VAT number. Check it on the document.'}
assert found(**{**gst_halves, 'seller_tax_id': '07AAHCA1234F1Z6'}) == \
    {'tax_id_invalid': '07AAHCA1234F1Z6 is not a valid GSTIN. Check it on the document.'}
assert found(**{**mehedi, 'tax': D('127.68'), 'total': D('978.88'), 'seller_tax_id': None}) == \
    {'tax_id_missing': 'No seller VAT number found. It is needed to claim this VAT back.'}
assert found(**{**gst_halves, 'seller_tax_id': None}) == {'tax_id_missing': 'No seller GSTIN found. It is needed to claim this GST back.'}
# the note only fires where a VAT/GST number is expected (BDT, INR, GBP, EUR); Indonesian local tax has none
assert found(**{**mehedi, 'tax': D('127.68'), 'total': D('978.88'), 'seller_tax_id': None, 'currency': 'IDR'}) == {}
assert found(**{**mehedi, 'tax': D('127.68'), 'total': D('978.88'), 'seller_tax_id': None, 'currency': None}) == {}
assert found(**{**maple, 'tax': D('6.15'), 'total': D('78.55')}) == {}  # US sales tax: no tax number needed
note = [i for i in validate(Document(**{**gst_halves, 'seller_tax_id': None}), today=TODAY)]
assert note[0]['level'] == 'note' and review(note) == []

from validate import older_than_upload
batch = [date(2026, 3, d) for d in (2, 9, 15)]
assert older_than_upload(date(2024, 1, 20), batch) == {
    'message': 'This document is dated 01/2024. The rest of this upload is from 03/2026.',
    'check': 'older_than_upload', 'fields': ['issue_date'], 'level': 'note'}
assert older_than_upload(date(2025, 11, 1), batch) is None  # within 6 months
assert older_than_upload(date(2024, 1, 20), batch[:2]) is None  # too few others to compare
assert older_than_upload(None, batch) is None
print('ok')
