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
for bad in ('{"total": "60.000"}', '{"items": [{"amount": "7,500"}]}', 'not json', '{"document": {"total": 5}}', '{"items": ["x"]}'):
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
from datetime import date
from eval_extract import text_match
assert text_match('vendor', 'Bradley-Andrade', 'Bradley-Andrade 9879 Elizabeth Common')
assert not text_match('vendor', 'Castro PLC', 'Bradley-Andrade 9879 Elizabeth Common') and not text_match('vendor', '', 'X')
assert text_match('doc_number', '97159829', '97159829') and not text_match('doc_number', '9715982', '97159829')
assert text_match('issue_date', date(2015, 9, 18), date(2015, 9, 18)) and text_match('currency', 'usd', 'USD')
s = score(Document(doc_number='1', total=D(5), items=[]), Document(doc_number='2', total=D(5), items=[]))
assert s['total'] and not s['doc_number'] and not s['all_correct']
# a sign error on the total is wrong; only discounts ignore sign
assert not score(Document(total=D(-100)), Document(total=D(100)))['total']
# 1-3 character names and longer wrong names do not match
assert not text_match('vendor', 'B', 'Bradley-Andrade 9879') and not text_match('vendor', 'Bradley-Andrade 9879 and more', 'Bradley-Andrade 9879')
assert parse('{"items": null, "total": 1}').items == []
assert parse('{"doc_type": "Invoice ", "total": 1}').doc_type == 'invoice' and parse('{"doc_type": "bill", "total": 1}').doc_type is None
from providers import mime
assert mime(b'%PDF-1.7') == 'application/pdf' and mime(b'\x89PNG\r\n') == 'image/png'
assert mime(b'\xff\xd8\xff\xe0') == 'image/jpeg' and mime(b'RIFF1234WEBPVP8 ') == 'image/webp' and mime(b'MZ\x90') is None
# timeouts and dropped connections are retried, then reported plainly
import providers, urllib.error
calls, real_open, real_sleep = [], providers.urllib.request.urlopen, providers.time.sleep
def flaky(req, timeout):
    calls.append(timeout)
    if len(calls) < 3:
        raise TimeoutError('The read operation timed out') if len(calls) == 1 else urllib.error.URLError('getaddrinfo failed')
    import io
    return io.BytesIO(b'{"ok": 1}')
providers.urllib.request.urlopen, providers.time.sleep = flaky, lambda s: None
assert providers.post('http://x', {}, {}) == ({'ok': 1}, 3) and calls == [60, 60, 60]
providers.urllib.request.urlopen = lambda req, timeout: (_ for _ in ()).throw(TimeoutError('slow'))
try:
    providers.post('http://x', {}, {})
    raise AssertionError('should raise')
except RuntimeError as e:
    assert 'no answer' in str(e)
providers.urllib.request.urlopen, providers.time.sleep = real_open, real_sleep
print('ok')
