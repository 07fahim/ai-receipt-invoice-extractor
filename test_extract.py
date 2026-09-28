from decimal import Decimal as D

from eval_extract import f1, name_f1, score
from providers import parse
from schema import Document, Item

# fences and think blocks stripped, doc_type case-insensitive
d = parse('<think>hmm</think>```json\n{"doc_type": "Receipt", "total": 60000, "items": []}\n```')
assert d.doc_type == 'receipt' and d.total == D(60000)
# text after the object is ignored (GLM adds a sentence)
assert parse('{"total": 5}\nEnd the code block.').total == D(5)
# amounts as text are rejected ("60.000" would silently become 60)
for bad in ('{"total": "60.000"}', '{"items": [{"amount": "7,500"}]}', 'not json'):
    try:
        parse(bad)
        raise AssertionError(bad)
    except ValueError:
        pass

assert f1([D(1), D(1), D(2)], [D(1), D(2)]) == 0.8 and f1([], []) == 1.0
assert name_f1(['AVOCADD COFFEE', 'Tea'], ['Avocado Coffee', 'Milk']) == 0.5

gold = Document(total=D(100), discount=D(-10), items=[Item(description='A', amount=D(110))])
s = score(Document(total=D(100), discount=D(10), items=[Item(description='a', amount=D(110))]), gold)
assert s['total'] and s['discount'] and s['all_correct']          # discount sign is a convention
s = score(Document(total=D(90), items=[Item(amount=D(110))]), gold)
assert not s['total'] and not s['discount'] and not s['all_correct'] and 'tax' not in s
print('ok')
