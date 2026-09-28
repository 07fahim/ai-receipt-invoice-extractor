"""Self-check for the API with a fake model (no model calls, no quota). Run: python test_app.py
Needs DATABASE_URL in .env; runs in its own temporary schema, dropped at the end."""
import io
import os
import uuid

os.environ['APP_SCHEMA'] = 'test_' + uuid.uuid4().hex[:8]

import pypdfium2
from fastapi.testclient import TestClient

import app
import providers

ANSWERS = {
    'good': '{"doc_type": "receipt", "vendor": "Green Field", "issue_date": "2016-05-26", "issue_date_text": "5/26/2016",'
            ' "currency": "USD", "subtotal": 51.90, "tax": 4.68, "total": 56.58,'
            ' "items": [{"description": "Coffee", "amount": 3.00}, {"description": "Lunch", "amount": 45.90},'
            ' {"description": "Coke", "amount": 3.00}]}',
    # 05/11/2021 is ambiguous; the model read it as 5 November
    'ambiguous': '{"vendor": "Nguyen-Roach", "issue_date": "2021-11-05", "issue_date_text": "05/11/2021",'
                 ' "subtotal": 10, "total": 10, "items": [{"amount": 10}]}',
}
calls = []


def fake_call(model, data):
    calls.append(data[:8])
    key = data[8:].decode(errors='ignore').strip()
    if key == 'boom':
        raise RuntimeError('HTTP 503: high demand')
    return ANSWERS[key], 100, 50, 1


providers.call = fake_call
c = TestClient(app.app)
JPG = b'\xff\xd8\xff\xe0\x00\x10JF'  # 8-byte JPEG header, then the answer key


def upload(*named):
    return c.post('/documents', files=[('files', (n, io.BytesIO(b), 'image/jpeg')) for n, b in named])


# upload: good file processed, fake .exe rejected
r = upload(('green.jpg', JPG + b'good'), ('virus.exe', b'MZ\x90\x00'))
assert r.status_code == 202, r.text
good_id = r.json()[0]['id']
assert 'error' in r.json()[1]
d = c.get(f'/documents/{good_id}').json()
assert d['status'] == 'passed' and d['vendor'] == 'Green Field' and d['total'] == 56.58 and 'file' not in d
assert d['model'] == app.MODEL and d['tokens_in'] == 100

# ambiguous date -> needs review; confirming the vendor's MDY order fixes the date and re-checks
amb_id = upload(('inv.jpg', JPG + b'ambiguous')).json()[0]['id']
d = c.get(f'/documents/{amb_id}').json()
assert d['status'] == 'needs_review' and d['checks'][0]['check'] == 'date_ambiguous'
r = c.put('/vendors/Nguyen-Roach/date-order', json={'date_order': 'MDY'}).json()
assert r['rechecked'] == 1
d = c.get(f'/documents/{amb_id}').json()
assert d['status'] == 'passed' and d['issue_date'] == '2021-05-11'
assert c.put('/vendors/x/date-order', json={'date_order': 'YMD'}).status_code == 422

# failed call is stored as failed; retry works once the model answers
bad_id = upload(('bad.jpg', JPG + b'boom')).json()[0]['id']
d = c.get(f'/documents/{bad_id}').json()
assert d['status'] == 'failed' and '503' in d['error']

# review: user corrects the total -> reviewed, checks run again
doc = c.get(f'/documents/{good_id}').json()['document']
doc['total'] = '60.00'
d = c.put(f'/documents/{good_id}', json=doc).json()
assert d['status'] == 'reviewed' and d['total'] == 60.0 and d['checks'][0]['check'] == 'total_math'

# history search and filters
assert [x['id'] for x in c.get('/documents', params={'q': 'green'}).json()] == [good_id]
assert [x['id'] for x in c.get('/documents', params={'status': 'failed'}).json()] == [bad_id]
assert [x['id'] for x in c.get('/documents', params={'date_from': '2021-01-01'}).json()] == [amb_id]

# stats: failed documents are not counted in spend
s = c.get('/stats').json()
assert s['documents'] == 3 and s['by_status'] == {'reviewed': 1, 'passed': 1, 'failed': 1}
assert {x['currency']: x['total'] for x in s['spend_by_currency']} == {'USD': 60.0, None: 10.0}

# pages: image = 1 page; PDF pages are rendered
assert c.get(f'/documents/{good_id}/pages').json() == {'pages': 1}
assert c.get(f'/documents/{good_id}/pages/1').status_code == 404
pdf = pypdfium2.PdfDocument.new()
pdf.new_page(200, 300); pdf.new_page(200, 300)
buf = io.BytesIO(); pdf.save(buf)
pdf_id = c.post('/documents', files=[('files', ('two.pdf', io.BytesIO(buf.getvalue()), 'application/pdf'))]).json()[0]['id']
assert c.get(f'/documents/{pdf_id}/pages').json() == {'pages': 2}
img = c.get(f'/documents/{pdf_id}/pages/1')
assert img.status_code == 200 and img.content[:4] == b'\x89PNG'

# export: CSV one row per non-failed document; XLSX has Documents + Items with numbers
from openpyxl import load_workbook
csv_text = c.get('/export', params={'format': 'csv'}).content.decode('utf-8-sig')
assert csv_text.splitlines()[0].startswith('id,file_name,status') and len(csv_text.splitlines()) == 3
wb = load_workbook(io.BytesIO(c.get('/export').content))
assert wb.sheetnames == ['Documents', 'Items'] and wb['Documents'].max_row == 3 and wb['Items'].max_row == 5
assert wb['Items']['E2'].value == 3.0 and c.get('/export', params={'format': 'pdf'}).status_code == 422

# delete removes the record and the file
assert c.delete(f'/documents/{good_id}').status_code == 204
assert c.get(f'/documents/{good_id}').status_code == 404 and c.get(f'/documents/{good_id}/file').status_code == 404
assert c.delete(f'/documents/{good_id}').status_code == 404
assert c.post('/documents', files=[]).status_code in (400, 422)
import store
with store.conn() as con:
    con.execute(f'DROP SCHEMA {store.schema_name()} CASCADE')
print('ok')
