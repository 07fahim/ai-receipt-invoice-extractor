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
print('ok')
