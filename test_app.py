"""Self-check for the API with a fake model (no model calls, no quota). Run: python test_app.py
Needs DATABASE_URL in .env; runs in its own temporary schema, dropped at the end.
Sign-in tokens are signed with a local test key instead of Supabase's."""
import csv
import io
import os
import time
import uuid

os.environ['APP_SCHEMA'] = 'test_' + uuid.uuid4().hex[:8]

import pypdfium2
from fastapi.testclient import TestClient

import jwt
from cryptography.hazmat.primitives.asymmetric import ec

import app
import providers

# sign-in: tokens like Supabase's (ES256, audience 'authenticated'), verified with a local test key
os.environ['SUPABASE_URL'] = 'https://test.supabase.co'
KEY, OTHER_KEY = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())
app.signing_key = lambda token: KEY.public_key()
ALICE, BOB, CAROL = (str(uuid.uuid4()) for _ in range(3))


def token(sub, key=KEY, **claims):
    body = {'sub': sub, 'aud': 'authenticated', 'iss': 'https://test.supabase.co/auth/v1', 'exp': int(time.time()) + 3600}
    return jwt.encode({**body, **claims}, key, algorithm='ES256')


def as_user(sub, **kw):
    return {'Authorization': f'Bearer {token(sub, **kw)}'}

ANSWERS = {
    'good': '{"doc_type": "receipt", "vendor": "Green Field", "branch": "017314", "issue_date": "2016-05-26", "issue_date_text": "5/26/2016",'
            ' "currency": "USD", "subtotal": 51.90, "tax": 4.68, "total": 56.58,'
            ' "items": [{"description": "Coffee", "amount": 3.00}, {"description": "Lunch", "amount": 45.90},'
            ' {"description": "Coke", "amount": 3.00}]}',
    # 05/11/2021 is ambiguous; the model read it as 5 November
    'ambiguous': '{"vendor": "Nguyen-Roach", "issue_date": "2021-11-05", "issue_date_text": "05/11/2021",'
                 ' "subtotal": 10, "total": 10, "items": [{"amount": 10}]}',
    'ambiguous2': '{"vendor": "Other Co", "issue_date": "2021-05-11", "issue_date_text": "05/11/2021",'
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

# a local webhook receiver standing in for n8n
import hashlib, hmac, json, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
events = []


class Hook(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers['Content-Length']))
        events.append((json.loads(body), self.headers['X-Signature'], body))
        self.send_response(200); self.end_headers()

    def log_message(self, *a):
        pass


hook = HTTPServer(('127.0.0.1', 0), Hook)
threading.Thread(target=hook.serve_forever, daemon=True).start()
os.environ['WEBHOOK_URL'] = f'http://127.0.0.1:{hook.server_port}/hook'
os.environ['WEBHOOK_SECRET'] = 'test-secret'
_send = app.send_event


def send_and_wait(doc_id):  # the app delivers on a side thread; tests wait so events can be checked
    worker = _send(doc_id)
    if worker:
        worker.join()


app.send_event = send_and_wait
c = TestClient(app.app, headers=as_user(ALICE))
try:
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
    # live checks without saving; a date format chosen for one document only resolves that document
    dave = as_user(str(uuid.uuid4()))  # own user, so Alice's counts below stay the same
    amb2 = c.post('/documents', files=[('files', ('inv2.jpg', io.BytesIO(JPG + b'ambiguous2'), 'image/jpeg'))], headers=dave).json()[0]['id']
    doc2 = c.get(f'/documents/{amb2}', headers=dave).json()['document']
    assert [x['check'] for x in c.post('/check', json=doc2, headers=dave).json()['checks']] == ['date_ambiguous']
    live = c.post('/check', json=doc2, params={'date_order': 'DMY'}, headers=dave).json()
    assert live['checks'] == [] and live['document']['issue_date'] == '2021-11-05'
    d = c.put(f'/documents/{amb2}', json=live['document'], params={'date_order': 'DMY'}, headers=dave).json()
    assert d['status'] == 'reviewed' and d['checks'] == [] and d['issue_date'] == '2021-11-05'
    assert c.post('/check', json=doc2, params={'date_order': 'YMD'}).status_code == 422

    # failed call is stored as failed with a short public message
    bad_id = upload(('bad.jpg', JPG + b'boom')).json()[0]['id']
    d = c.get(f'/documents/{bad_id}').json()
    assert d['status'] == 'failed' and 'busy' in d['error'] and 'HTTP' not in d['error']  # no raw provider text

    # retry: a failed document can be retried; it is extracted again
    assert c.post(f'/documents/{bad_id}/retry').status_code == 202 and c.get(f'/documents/{bad_id}').json()['status'] == 'failed'

    # review: user corrects the total -> reviewed, checks run again
    doc = c.get(f'/documents/{good_id}').json()['document']
    doc['total'] = '60.00'
    d = c.put(f'/documents/{good_id}', json=doc).json()
    assert d['status'] == 'reviewed' and d['total'] == 60.0 and d['checks'][0]['check'] == 'total_math'

    # webhook: sent for passed documents and after review, signed with the secret; not for needs_review/failed
    kinds = [(e['event'], e['id']) for e, _, _ in events]
    assert kinds == [('document.passed', good_id), ('document.passed', amb_id), ('document.reviewed', amb2),
                     ('document.reviewed', good_id)], kinds
    e, sig, raw = events[-1]
    assert sig == 'sha256=' + hmac.new(b'test-secret', raw, hashlib.sha256).hexdigest() and e['document']['total'] == '60.00'

    # a reviewed document cannot be retried (the user's corrections would be lost)
    assert c.post(f'/documents/{good_id}/retry').status_code == 409
    assert c.get(f'/documents/{good_id}').json()['total'] == 60.0

    # bad query values are 422, not server errors
    for bad_q in ({'date_from': 'nope'}, {'limit': -1}, {'offset': -1}, {'limit': 0}):
        assert c.get('/documents', params=bad_q).status_code == 422, bad_q

    # history search and filters
    assert [x['id'] for x in c.get('/documents', params={'q': 'green'}).json()] == [good_id]
    assert [x['id'] for x in c.get('/documents', params={'status': 'failed'}).json()] == [bad_id]
    assert [x['id'] for x in c.get('/documents', params={'date_from': '2021-01-01'}).json()] == [amb_id]

    # stats: spend counts only checked documents (passed or reviewed), never failed or waiting ones
    s = c.get('/stats').json()
    assert s['documents'] == 3 and s['by_status'] == {'reviewed': 1, 'passed': 1, 'failed': 1}
    assert {x['currency']: x['total'] for x in s['spend_by_currency']} == {'USD': 60.0, None: 10.0}
    erin = as_user(str(uuid.uuid4()))  # a document waiting for review is not spend yet
    c.post('/documents', files=[('files', ('w.jpg', io.BytesIO(JPG + b'ambiguous'), 'image/jpeg'))], headers=erin)
    s = c.get('/stats', headers=erin).json()
    assert s['by_status'] == {'needs_review': 1} and s['spend_by_currency'] == [] and s['top_vendors'] == [] and s['by_month'] == []

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
    # a huge page renders at most 2000 px; unreadable or 21-page PDFs are rejected at upload
    from PIL import Image
    big = pypdfium2.PdfDocument.new(); big.new_page(14400, 14400); buf = io.BytesIO(); big.save(buf)
    big_id = c.post('/documents', files=[('files', ('big.pdf', io.BytesIO(buf.getvalue()), 'application/pdf'))]).json()[0]['id']
    assert max(Image.open(io.BytesIO(c.get(f'/documents/{big_id}/pages/0').content)).size) <= 2000
    many = pypdfium2.PdfDocument.new()
    for _ in range(21):
        many.new_page(100, 100)
    buf = io.BytesIO(); many.save(buf)
    bad = c.post('/documents', files=[('files', ('many.pdf', io.BytesIO(buf.getvalue()), 'application/pdf')),
                                      ('files', ('broken.pdf', io.BytesIO(b'%PDF-1.7 garbage'), 'application/pdf'))]).json()
    assert all('error' in x for x in bad), bad

    # export: CSV one row per non-failed document; XLSX has Documents + Items with numbers
    from openpyxl import load_workbook
    csv_text = c.get('/export', params={'format': 'csv'}).content.decode('utf-8-sig')
    assert csv_text.splitlines()[0].startswith('id,file_name,status') and len(csv_text.splitlines()) == 3
    assert 'vendor,branch,buyer' in csv_text.splitlines()[0] and ',Green Field,017314,' in csv_text
    wb = load_workbook(io.BytesIO(c.get('/export').content))
    assert wb.sheetnames == ['Documents', 'Items'] and wb['Documents'].max_row == 3 and wb['Items'].max_row == 5
    assert wb['Items']['E2'].value == 3.0 and c.get('/export', params={'format': 'pdf'}).status_code == 422
    # text stays text (leading zeros kept) and a formula from a document is never run by the spreadsheet
    ANSWERS['formula'] = ('{"vendor": "=HYPERLINK(\\"http://evil\\")", "doc_number": "00123", "total": 5,'
                          ' "items": [{"description": "2023", "amount": 5}]}')
    f_id = upload(('f.jpg', JPG + b'formula')).json()[0]['id']
    ws = load_workbook(io.BytesIO(c.get('/export', params={'status': 'passed'}).content))['Documents']
    row_ = {h.value: cell.value for h, cell in zip(ws[1], ws[ws.max_row])}
    assert row_['id'] == f_id and row_['doc_number'] == '00123' and row_['vendor'].startswith("'=") and row_['total'] == 5.0
    assert ws.cell(ws.max_row, 5).data_type != 'f'
    items = load_workbook(io.BytesIO(c.get('/export').content))['Items']
    assert items.cell(items.max_row, 2).value == '2023'
    assert "'=HYPERLINK" in c.get('/export', params={'format': 'csv', 'status': 'passed'}).content.decode('utf-8-sig')

    # QuickBooks bills: one row per line, lines add up to the total; a cash-rounded total becomes one line;
    # documents without a date are skipped and counted
    ANSWERS['rounded'] = ('{"vendor": "Round Co", "doc_number": "R1", "issue_date": "2024-01-02", "subtotal": 1000,'
                          ' "total": 1000.40, "items": [{"description": "Rice", "amount": 1000}]}')
    upload(('r.jpg', JPG + b'rounded'))
    qb_id = upload(('g2.jpg', JPG + b'good')).json()[0]['id']
    r = c.get('/export', params={'format': 'quickbooks'})
    qb = list(csv.reader(r.content.decode('utf-8-sig').splitlines()))
    assert qb[0][:3] == ['Bill no.', 'Supplier', 'Bill Date'] and int(r.headers['x-skipped']) >= 1
    first = [x for x in qb if x[0] == f'CC-{qb_id}']
    assert [(x[5], x[6]) for x in first] == [('Coffee', '3.00'), ('Lunch', '45.90'), ('Coke', '3.00'), ('Tax', '4.68')]
    # the reviewed document whose total no longer matches its lines becomes a single line
    assert [(x[5], x[6]) for x in qb if x[0] == f'CC-{good_id}'] == [('Total', '60.00')]
    assert first[0][1:5] == ['Green Field', '05/26/2016', '05/26/2016', 'Uncategorized Expense']
    assert [(x[5], x[6]) for x in qb if x[1] == 'Round Co'] == [('Total', '1000.40')]

    # any-language file names download fine
    uni_id = upload(('領収書.jpg', JPG + b'good')).json()[0]['id']
    r = c.get(f'/documents/{uni_id}/file')
    assert r.status_code == 200 and "filename*=UTF-8''" in r.headers['content-disposition'] and r.content.startswith(JPG)

    # sign-in required on every endpoint; expired, wrong-audience and forged tokens are refused
    routes = [(m, rt.path.replace('{doc_id}', str(good_id)).replace('{n}', '0').replace('{vendor}', 'x'))
              for rt in app.app.routes if getattr(rt, 'endpoint', None) and rt.path.split('/')[1] not in ('docs', 'openapi.json', 'redoc')
              for m in rt.methods - {'HEAD'}]
    assert len(routes) == 13, routes
    anon = TestClient(app.app)
    for m, path in routes:
        assert anon.request(m, path).status_code == 401, (m, path)
    for bad in ({'exp': int(time.time()) - 10}, {'aud': 'anon'}, {'key': OTHER_KEY}):
        assert c.get('/documents', headers=as_user(ALICE, **bad)).status_code == 401, bad
    assert c.get('/documents', headers={'Authorization': 'Basic abc'}).status_code == 401

    # the web app's origin may call the API from the browser; other sites may not
    pre = {'Access-Control-Request-Method': 'GET', 'Access-Control-Request-Headers': 'authorization'}
    assert anon.options('/documents', headers={'Origin': 'http://localhost:3000', **pre}).headers['access-control-allow-origin'] == 'http://localhost:3000'
    assert 'access-control-allow-origin' not in anon.options('/documents', headers={'Origin': 'https://evil.example', **pre}).headers

    # another user sees none of Alice's documents and cannot change them
    bob = as_user(BOB)
    assert c.get('/documents', headers=bob).json() == [] and c.get('/stats', headers=bob).json()['documents'] == 0
    doc = c.get(f'/documents/{good_id}').json()['document']
    for m, path, body in (('GET', '', None), ('PUT', '', doc), ('DELETE', '', None), ('POST', '/retry', None),
                          ('GET', '/file', None), ('GET', '/pages', None), ('GET', '/pages/0', None)):
        assert c.request(m, f'/documents/{good_id}{path}', json=body, headers=bob).status_code == 404, (m, path)
    assert c.get('/export', params={'format': 'csv'}, headers=bob).content.decode('utf-8-sig').count('\n') == 1
    assert c.get('/export', params={'format': 'quickbooks'}, headers=bob).content.decode('utf-8-sig').count('\n') == 1
    # Bob's date format for a vendor re-checks only his own documents
    assert c.put('/vendors/Green Field/date-order', json={'date_order': 'DMY'}, headers=bob).json()['rechecked'] == 0
    assert c.get(f'/documents/{good_id}').status_code == 200

    # daily upload limit per user: files over the limit are refused, then the whole request
    app.DAILY_UPLOAD_LIMIT = 2
    carol = as_user(CAROL)
    three = [('files', (f'{k}.jpg', io.BytesIO(JPG + b'good'), 'image/jpeg')) for k in range(3)]
    r = c.post('/documents', files=three, headers=carol).json()
    assert ['id' in x for x in r] == [True, True, False] and 'daily limit' in r[2]['error']
    assert c.post('/documents', files=[('files', ('x.jpg', io.BytesIO(JPG + b'good'), 'image/jpeg'))], headers=carol).status_code == 429
    app.DAILY_UPLOAD_LIMIT = 50

    # delete removes the record and the file
    assert c.delete(f'/documents/{good_id}').status_code == 204
    assert c.get(f'/documents/{good_id}').status_code == 404 and c.get(f'/documents/{good_id}/file').status_code == 404
    assert c.delete(f'/documents/{good_id}').status_code == 404
    assert c.post('/documents', files=[]).status_code in (400, 422)
    # size limits: an 11 MB file is refused; a request larger than 20 files x 10 MB is refused before reading
    over = c.post('/documents', files=[('files', ('big.jpg', io.BytesIO(JPG + b'0' * (10 * 1024 * 1024)), 'image/jpeg'))]).json()
    assert 'error' in over[0]
    assert c.post('/documents', content=b'x', headers={'content-length': str(300 * 1024 * 1024),
                                                       'content-type': 'multipart/form-data; boundary=x'}).status_code == 413
    assert c.post('/documents', files=[('files', (f'{k}.jpg', io.BytesIO(JPG + b'good'), 'image/jpeg')) for k in range(21)]).status_code == 400
    print('ok')
finally:
    import store
    with store.conn() as con:
        con.execute(f'DROP SCHEMA {store.schema_name()} CASCADE')
