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
assert parse('{"branch": "MUSHAK-6.3", "total": 1}').branch is None and parse('{"branch": "Gulshan-1", "total": 1}').branch == 'Gulshan-1'
assert parse('{"doc_type": "Invoice ", "total": 1}').doc_type == 'invoice' and parse('{"doc_type": "bill", "total": 1}').doc_type is None
assert parse('{"document_count": 2, "total": 1}').document_count == 2
assert parse('{"is_document": false}').is_document is False and parse('{"is_document": "no", "total": 1}').is_document is None
assert parse('{"tax_included": true, "total": 1}').tax_included is True and parse('{"tax_included": "yes", "total": 1}').tax_included is None
# a quantity with its unit keeps the number (Bangla digits too); an unreadable quantity is dropped, not fatal;
# money written as text still fails the document
q = lambda s: parse('{"total": 1, "items": [{"quantity": %s, "amount": 1}]}' % json.dumps(s)).items[0].quantity
import json
assert q('২ কেজি') == 2 and q('1 dozen') == 1 and q('0.5 kg') == D('0.5') and q('১২.৫') == D('12.5')
assert q('a few') is None and q(3) == 3
try:
    parse('{"total": "60.000"}')
    raise AssertionError('should raise')
except ValueError:
    pass
assert parse('{"document_count": "two", "total": 1}').document_count is None and parse('{"document_count": true}').document_count is None
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
# a per-minute 429 is retried; a used-up daily quota is not (waiting can't help), and says so
def quota(window):
    def refuse(req, timeout):
        calls.append(window)
        body = '{"error": {"code": 429, "details": [{"violations": [{"quotaId": "GenerateRequests%sPerProjectPerModel-FreeTier"}]}]}}' % window
        raise urllib.error.HTTPError('http://x', 429, 'Too Many Requests', {}, io.BytesIO(body.encode()))
    return refuse
import io
for window, tries in (('PerMinute', 4), ('PerDay', 1)):
    calls.clear()
    providers.urllib.request.urlopen = quota(window)
    try:
        providers.post('http://x', {}, {})
        raise AssertionError('should raise')
    except RuntimeError as e:
        assert len(calls) == tries and (('daily quota used up' in str(e)) == (window == 'PerDay')), (window, calls, e)
providers.urllib.request.urlopen, providers.time.sleep = real_open, real_sleep

# seven decimals are rounded to six instead of failing the document
d = parse('{"total": 1.0, "items": [{"description": "x", "unit_price": 0.3333333, "amount": 1.0}]}')
assert str(d.items[0].unit_price) == '0.333333', d.items[0].unit_price

# the second-reading model thinks at the level we measured ("low"); other models send no thinking setting
sent = []
real_post = providers.post
providers.post = lambda url, headers, body, **kw: (sent.append(body), ({'candidates': [{'content': {'parts': [{'text': '{}'}]}}]}, 1))[1]
providers.os.environ.setdefault('GEMINI_API_KEY', 'test')
providers.call('gemini-3.5-flash', b'\xff\xd8\xff\xe0')
providers.call('gemini-3.1-flash-lite', b'\xff\xd8\xff\xe0')
providers.post = real_post
assert sent[0]['generationConfig']['thinkingConfig'] == {'thinkingLevel': 'low'}, sent[0]
assert 'thinkingConfig' not in sent[1]['generationConfig'], sent[1]

from providers import parse as parse_rates
d = parse_rates('{"total": 10, "tax_rate": "15%", "tax_kind": "VAT", "discount_rate": 250, "seller_tax_id": " GB123 4567 82 "}')
assert (d.tax_rate, d.tax_kind, d.discount_rate, d.seller_tax_id) == (15, 'vat', None, 'GB123 4567 82'), d
d = parse_rates('{"total": 10, "tax_rate": 7.5, "tax_kind": "state tax", "discount_rate": 10, "seller_tax_id": ""}')
assert (d.tax_rate, d.tax_kind, d.discount_rate, d.seller_tax_id) == (D('7.5'), None, 10, None), d
# a tax number with no letters comes back as a JSON number, not a string: must not become None
d = parse_rates('{"total": 10, "seller_tax_id": 123456789}')
assert d.seller_tax_id == '123456789', d
d = parse_rates('{"total": 10, "seller_tax_id": true}')
assert d.seller_tax_id is None, d  # bool is an int subclass: must not pass through as "True"
d = parse_rates('{"total": 10, "seller_tax_id": "Applied"}')
assert d.seller_tax_id is None, d  # "BIN: Applied" on Arax: a word, not a number

print('ok')
