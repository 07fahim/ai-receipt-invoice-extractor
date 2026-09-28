from cord import fields
from eval_ocr import score_doc, word_recall

lines = ['- TICKET CP', 'Rp60.000', 'TOTAL (QtY 2.00 60,000', 'TAX 5.455', 'PB1']


def found(pairs):
    return [ok for _, _, ok in score_doc(pairs, lines)]


# numbers match on digits regardless of separators / currency prefix; 6000 is not 60000
assert found([('total', '60.000'), ('tax', '5.455'), ('subtotal', '6.000')]) == [True, True, False]
# item numbers use each token once (two 60000 tokens), totals only need to appear somewhere
assert found([('item_amount', '60.000'), ('item_amount', '60.000'), ('item_amount', '60.000'), ('total', '60.000')]) == [True, True, False, True]
# qty "1" can match "PB1" only once
assert found([('item_qty', '1'), ('item_qty', '1')]) == [True, False]
# no-digit values in numeric fields are skipped, not counted as found
assert score_doc([('tax', '-')], lines) == []
# text fields ignore case and spaces
assert found([('item_name', '-TICKET CP'), ('item_name', 'COFFEE')]) == [True, False]

assert abs(word_recall(['TAX', '5.455', 'MISSING'], lines) - 2 / 3) < 1e-9

# CORD: single item as dict, several as list; itemsubtotal used when price missing; list values kept
assert fields({'menu': {'nm': 'A', 'price': '1'}, 'total': {'total_price': '1'}}) == \
    [('item_name', 'A'), ('item_amount', '1'), ('total', '1')]
assert fields({'menu': [{'nm': 'A', 'unitprice': '2', 'itemsubtotal': '4'}, {'nm': 'B'}]}) == \
    [('item_name', 'A'), ('item_unit_price', '2'), ('item_amount', '4'), ('item_name', 'B')]
assert fields({'sub_total': {'subtotal_price': ['46.636', '46.636']}}) == [('subtotal', '46.636')] * 2
from decimal import Decimal as D
from cord import parse_amount, to_document
assert [parse_amount(x) for x in ('60.000', '1,591,600', '9.999,99', '99,999.99', 'Rp. 111,000', '-60.000', '99 -', '-', '100%', '2.00')] == \
    [D(60000), D(1591600), D('9999.99'), D('99999.99'), D(111000), D(-60000), D(-99), None, None, D('2.00')]
d = to_document({'menu': {'nm': 'Tea', 'price': '24,000', 'discountprice': '-4,000',
                          'sub': [{'nm': 'Jelly', 'price': '4,000'}, {'nm': 'Less Ice'}]},
                 'total': {'total_etc': '24.000'}})
assert [(i.description, i.amount, i.discount) for i in d.items] == [('Tea', D(24000), D(-4000)), ('Jelly', D(4000), None)]
assert d.total == D(24000)
print('ok')
