import csv
from datetime import date
import io
import os
import time
import urllib.error
import urllib.request
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
    # the same invoice twice (number printed differently), and the vendor's next invoice
    'inv1042': '{"vendor": "ABC Ltd", "doc_number": "INV-1042", "total": 20, "items": [{"amount": 20}]}',
    'inv1042b': '{"vendor": "ABC Limited.", "doc_number": "#inv 1042", "total": 20, "items": [{"amount": 20}]}',
    'inv1043': '{"vendor": "ABC Ltd", "doc_number": "INV-1043", "total": 20, "items": [{"amount": 20}]}',
    # a handwritten memo: line 2 read as 280 (2 x 120 is 240), date 20/06 (printed 20/05)
    'memo': '{"vendor": "Fruit Store", "issue_date": "2024-06-20", "issue_date_text": "20/06/2024", "subtotal": 1230, "total": 1230,'
            ' "items": [{"quantity": 2, "unit_price": 140, "amount": 280}, {"quantity": 2, "unit_price": 120, "amount": 280},'
            ' {"quantity": 1, "unit_price": 710, "amount": 710}]}',
    # a real check (item sum) fails, and 05/11/2021 is ambiguous: the two readings print the same text but take it the other way
    'dateamb': '{"vendor": "Datevendor", "issue_date": "2021-11-05", "issue_date_text": "05/11/2021", "subtotal": 1230, "total": 1230,'
               ' "items": [{"quantity": 2, "unit_price": 140, "amount": 280}, {"quantity": 2, "unit_price": 120, "amount": 280},'
               ' {"quantity": 1, "unit_price": 710, "amount": 710}]}',
    # passes every check; the second reading disagrees on the total (meaningful)
    'pass2': '{"vendor": "Acme Co", "subtotal": 100, "tax": 10, "total": 110, "items": [{"amount": 100}]}',
    # passes every check; the second reading differs only in vendor case and an extra 0.00 line (not meaningful)
    'pass3': '{"vendor": "Beta Inc", "subtotal": 50, "tax": 5, "total": 55, "items": [{"amount": 50}]}',
    # a real check (items_sum) fails; fake_call fixes the stored document (simulating a concurrent re-save)
    # while the second model call is "in flight", so second_read must decide on the fixed document, not the stale one
    'race': '{"vendor": "Race Co", "subtotal": 100, "total": 100, "items": [{"amount": 90}]}',
}
calls = []

SECOND = {  # what the second-reading model says, by file
    'memo': ANSWERS['memo'].replace('"amount": 280}, {"quantity": 1', '"amount": 240}, {"quantity": 1')
                           .replace('2024-06-20", "issue_date_text": "20/06/2024', '2024-05-20", "issue_date_text": "20/05/2024'),
    'memo4': ANSWERS['memo'].replace('"amount": 710}]', '"amount": 710}, {"quantity": 1, "unit_price": 0, "amount": 0}]'),
    'dateamb': ANSWERS['dateamb'].replace('"issue_date": "2021-11-05"', '"issue_date": "2021-05-11"'),
    'pass2': ANSWERS['pass2'].replace('"total": 110', '"total": 120'),
    'pass3': ANSWERS['pass3'].replace('"vendor": "Beta Inc"', '"vendor": "BETA INC"')
                             .replace('"items": [{"amount": 50}]', '"items": [{"amount": 50}, {"amount": 0}]'),
}


def fake_call(model, data):
    calls.append(data[:8])
    key = data[8:].decode(errors='ignore').strip()
    if key == 'boom':
        raise RuntimeError('HTTP 503: high demand')
    if model == app.SECOND_MODEL:
        if key == 'memoq':
            raise RuntimeError('daily quota used up: HTTP 429')
        if key == 'race':
            # a concurrent re-save (e.g. a vendor date-order re-check) lands while this call is in flight
            with store.conn() as con:
                con.execute("UPDATE documents SET document = jsonb_set(document, '{items,0,amount}', '\"100\"'::jsonb) "
                           "WHERE document->>'vendor' = 'Race Co'")
        return SECOND.get(key, ANSWERS[key.rstrip('q4') if key.startswith('memo') else key]), 100, 50, 1
    return ANSWERS[key.rstrip('q4') if key.startswith('memo') else key], 100, 50, 1


providers.call = fake_call


def second_done():
    # SECOND_WORKER is a single FIFO worker: waiting for a no-op submitted now waits for everything queued before it
    app.SECOND_WORKER.submit(lambda: None).result()

# a local webhook receiver standing in for n8n
import contextlib, hashlib, hmac, http.client, json, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
events, own_events, arrived = [], [], []  # the server's n8n (/hook), one user's own address (/own), arrival order of both


class Hook(BaseHTTPRequestHandler):
    fail, slow = 0, 0  # answer 500 to the next `fail` posts to /own; wait `slow` seconds before answering /own

    def do_POST(self):
        body = self.rfile.read(int(self.headers['Content-Length']))
        if self.path == '/drip':  # answers one byte at a time, for 4 seconds
            with contextlib.suppress(OSError):  # the sender cuts it off
                for ch in b'HTTP/1.1 200 OK\r\nX-Slow: ' + b'x' * 8:
                    self.wfile.write(bytes([ch])); self.wfile.flush(); time.sleep(0.25)
            return
        if self.path == '/redirect':
            self.send_response(302); self.send_header('Location', '/hook'); self.end_headers()
            return
        if self.path == '/own':
            time.sleep(Hook.slow)
            if Hook.fail:
                Hook.fail -= 1
                self.send_response(500); self.end_headers()
                return
        (events if self.path == '/hook' else own_events).append((json.loads(body), self.headers['X-Signature'], body))
        arrived.append(self.path)
        self.send_response(200); self.end_headers()

    def log_message(self, *a):
        pass


hook = ThreadingHTTPServer(('127.0.0.1', 0), Hook)
threading.Thread(target=hook.serve_forever, daemon=True).start()
os.environ['WEBHOOK_URL'] = f'http://127.0.0.1:{hook.server_port}/hook'
os.environ['WEBHOOK_SECRET'] = 'test-secret'
os.environ['WEBHOOK_USER_ID'] = f' {ALICE.upper()} ,'  # only Alice's documents go to the webhook (spaces, case, commas ignored)
sender = []


def flush():
    # waits until every due webhook event is sent. The first call starts the sender, like a server starting
    # with events saved before a restart: everything queued until then must still arrive.
    if not sender:
        sender.append(threading.Thread(target=app.deliver_events, daemon=True))
        sender[0].start()
    app.WAKE.set()
    for _ in range(400):
        time.sleep(0.05)
        with store.conn() as con:
            due = con.execute('SELECT count(*) AS n FROM webhook_events WHERE next_at <= now()').fetchone()['n']
        if not due and not app.SENDING:
            return
    raise AssertionError('webhook events were not sent')
c = TestClient(app.app, headers=as_user(ALICE))
app.DAILY_UPLOAD_LIMIT = 50  # these tests upload more than the default 10; the limit test sets its own
app.SECOND_READ_DAILY_LIMIT = 200  # passed documents now also queue second reads; avoid tripping the cap in unrelated tests
app.SECOND_READ_PER_USER = 50
import store
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
    r = c.put('/vendors/nguyen roach ltd/date-order', json={'date_order': 'MDY'}).json()
    assert r['rechecked'] == 1
    d = c.get(f'/documents/{amb_id}').json()
    assert d['status'] == 'passed' and d['issue_date'] == '2021-05-11'
    assert c.put('/vendors/x/date-order', json={'date_order': 'YMD'}).status_code == 422
    # a vendor printed with a slash (M/S Rahman Traders) still reaches the route
    assert c.put('/vendors/M%2FS Rahman Traders/date-order', json={'date_order': 'DMY'}).status_code == 200
    # one vendor however it is printed (date memory and duplicates use this)
    vk = app.store.vendor_key
    assert vk('SHWAPNO') == vk('Shwapno Ltd.') == vk('Shwapno Limited') == vk('Shwapno Pvt. Ltd.') == 'shwapno'
    assert vk('Co') == 'co' and vk('Chapman, Kim and Green') == 'chapman kim and green' and vk(None) == ''
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
    # a document the user checks or saves counts as one document, whatever the model said
    notdoc = c.post('/check', json={**doc2, 'is_document': False, 'document_count': 2}, params={'date_order': 'DMY'}, headers=dave).json()
    assert not {x['check'] for x in notdoc['checks']} & {'not_a_document', 'one_document'}, notdoc['checks']
    # a misread digit that breaks two checks comes with a suggested fix; a clean document with none
    memo = {'subtotal': '1230', 'total': '1230', 'items': [{'quantity': '2', 'unit_price': '140', 'amount': '280'},
            {'quantity': '2', 'unit_price': '120', 'amount': '280'}, {'quantity': '1', 'unit_price': '710', 'amount': '710'}]}
    assert c.post('/check', json=memo, headers=dave).json()['suggestion']['changes'] == [{'field': 'items[1].amount', 'from': '280', 'to': '240'}]
    assert c.post('/check', json=live['document'], headers=dave).json()['suggestion'] is None
    assert c.get(f'/documents/{amb2}', headers=dave).json()['suggestion'] is None  # reviewed: nothing to suggest

    # failed call is stored as failed with a short public message
    assert 'limit is used up' in app.public_error(RuntimeError('daily quota used up: HTTP 429: {...}'))
    bad_id = upload(('bad.jpg', JPG + b'boom')).json()[0]['id']
    d = c.get(f'/documents/{bad_id}').json()
    assert d['status'] == 'failed' and 'busy' in d['error'] and 'HTTP' not in d['error']  # no raw provider text

    # retry: a failed document can be retried; it is extracted again
    assert c.post(f'/documents/{bad_id}/retry').status_code == 202 and c.get(f'/documents/{bad_id}').json()['status'] == 'failed'

    # a restart while a document was being read: at startup it is read again instead of staying 'processing'
    hank = str(uuid.uuid4())
    with store.conn() as con:
        stuck = con.execute("INSERT INTO documents (user_id, file_name, mime, file, status) "
                            "VALUES (%s, 's.jpg', 'image/jpeg', %s, 'processing') RETURNING id", (hank, JPG + b'good')).fetchone()['id']
    assert app.resume_stuck() == [stuck] and c.get(f'/documents/{stuck}', headers=as_user(hank)).json()['status'] == 'passed'
    assert app.resume_stuck() == []

    # review: user corrects the total -> reviewed, checks run again
    doc = c.get(f'/documents/{good_id}').json()['document']
    doc['total'] = '60.00'
    d = c.put(f'/documents/{good_id}', json=doc).json()
    assert d['status'] == 'reviewed' and d['total'] == 60.0 and d['checks'][0]['check'] == 'total_math'
    # the AI's first reading is kept apart from the correction, to measure how often people fix it
    with app.store.conn() as con:
        kept = con.execute('SELECT extracted, document FROM documents WHERE id = %s', (good_id,)).fetchone()
    assert kept['extracted']['total'] == '56.58' and kept['document']['total'] == '60.00'
    import corrections
    assert corrections.report([(kept['extracted'], kept['document'])]) == [
        '1 reviewed documents, 1 corrected (100%)', '1 of the corrected ones had passed every check (mistakes the checks missed)',
        'Fields changed: total 1']
    assert corrections.report([(kept['extracted'], kept['extracted'])])[0] == '1 reviewed documents, 0 corrected (0%)'
    padded = {**kept['extracted'], 'subtotal': '51.90', 'vendor': ' Green Field '}  # how the review screen shows it: not a correction
    assert corrections.report([(kept['extracted'], padded)])[0] == '1 reviewed documents, 0 corrected (0%)'

    # webhook: every reading (passed, needs_review, failed) and every review, signed with the secret
    assert not events  # no sender yet: the events wait in the table
    flush()
    kinds = [(e['event'], e['id']) for e, _, _ in events]
    # Dave's reviewed document and the resumed one belong to other users: not sent
    assert kinds == [('document.passed', good_id), ('document.needs_review', amb_id), ('document.passed', amb_id),
                     ('document.failed', bad_id), ('document.failed', bad_id), ('document.reviewed', good_id)], kinds
    failed_event = next(e for e, _, _ in events if e['event'] == 'document.failed')
    assert 'busy' in failed_event['error'] and 'HTTP' not in failed_event['error']  # the short public message only
    e, sig, raw = events[-1]
    assert sig == 'sha256=' + hmac.new(b'test-secret', raw, hashlib.sha256).hexdigest() and e['document']['total'] == '60.00'
    assert len({e['event_id'] for e, _, _ in events}) == len(events)  # receivers can drop repeats by event_id

    # a reviewed document cannot be retried (the user's corrections would be lost)
    assert c.post(f'/documents/{good_id}/retry').status_code == 409
    assert c.get(f'/documents/{good_id}').json()['total'] == 60.0
    # two tabs: a save based on an older version is refused, the current version saves
    opened = c.get(f'/documents/{good_id}').json()
    newer = c.put(f'/documents/{good_id}', json=opened['document'], params={'if_unchanged_since': opened['updated_at']})
    assert newer.status_code == 200
    stale = c.put(f'/documents/{good_id}', json=opened['document'], params={'if_unchanged_since': opened['updated_at']})
    assert stale.status_code == 409 and 'another tab' in stale.json()['detail']
    # while a document is being read: no second read, no save; a late read never replaces saved corrections
    with store.conn() as con:
        con.execute("UPDATE documents SET status = 'processing' WHERE id = %s", (good_id,))
    assert c.post(f'/documents/{good_id}/retry').status_code == 409
    assert c.put(f'/documents/{good_id}', json=c.get(f'/documents/{good_id}').json()['document']).status_code == 409
    with store.conn() as con:
        con.execute("UPDATE documents SET status = 'reviewed' WHERE id = %s", (good_id,))
    app.process(good_id)  # the fake model answers again, but the document is no longer 'processing'
    assert c.get(f'/documents/{good_id}').json()['status'] == 'reviewed'

    # bad query values are 422, not server errors
    for bad_q in ({'date_from': 'nope'}, {'limit': -1}, {'offset': -1}, {'limit': 0}):
        assert c.get('/documents', params=bad_q).status_code == 422, bad_q

    # history search and filters
    assert [x['id'] for x in c.get('/documents', params={'q': 'green'}).json()] == [good_id]
    assert c.get('/documents', params={'q': '%'}).json() == [] and c.get('/documents', params={'q': '_'}).json() == []  # literal, not wildcards
    assert [x['id'] for x in c.get('/documents', params={'status': 'failed'}).json()] == [bad_id]
    ids_newest = [x['id'] for x in c.get('/documents').json()]
    assert [x['id'] for x in c.get('/documents', params={'oldest': 'true'}).json()] == ids_newest[::-1]  # review queue order
    assert [x['id'] for x in c.get('/documents', params={'date_from': '2021-01-01'}).json()] == [amb_id]

    # stats: spend counts only checked documents (passed or reviewed), never failed or waiting ones
    s = c.get('/stats').json()
    assert s['documents'] == 3 and s['by_status'] == {'reviewed': 1, 'passed': 1, 'failed': 1}
    assert {x['currency']: x['total'] for x in s['spend_by_currency']} == {'USD': 60.0, None: 10.0}
    assert sum(x['total'] for x in s['tax_by_currency']) > 0
    # a date range narrows the money figures (the 2016 receipt drops out) but not the counts
    later = c.get('/stats', params={'date_from': '2021-01-01'}).json()
    assert later['documents'] == 3 and later['by_status'] == s['by_status']
    assert all(m['month'] >= '2021-01' for m in later['by_month']) and sum(x['n'] for x in later['spend_by_currency']) < sum(x['n'] for x in s['spend_by_currency'])
    assert c.get('/stats', params={'date_from': 'soon'}).status_code == 422
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
    dates = {h.value: x for h, x in zip(wb['Documents'][1], wb['Documents'][2])}
    assert dates['issue_date'].value.date() == date(2016, 5, 26) and dates['issue_date'].number_format == 'yyyy-mm-dd'  # a real date
    assert dates['due_date'].value is None and '2016-05-26' in csv_text  # CSV keeps ISO text
    # columns fit their values (dates never show as ####) and the header row stays in view
    letter, dims = dates['issue_date'].column_letter, wb['Documents'].column_dimensions
    assert letter in dims and dims[letter].width >= 12  # unset columns are not saved at all
    assert wb['Documents'].freeze_panes == 'A2' and wb['Items'].freeze_panes == 'A2'
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
    ANSWERS['rounded'] = ('{"vendor": "Round Co", "doc_number": "R1", "issue_date": "2024-01-02", "subtotal": 999.60,'
                          ' "total": 1000, "items": [{"description": "Rice", "amount": 999.60}]}')
    upload(('r.jpg', JPG + b'rounded'))
    # "VAT included": passes the checks, and the bill keeps its item lines without adding the VAT again
    ANSWERS['vatincl'] = ('{"vendor": "Green Basket", "doc_number": "GB1", "issue_date": "2026-09-18", "currency": "BDT",'
                          ' "subtotal": 1150, "tax": 150, "tax_included": true, "total": 1150,'
                          ' "items": [{"description": "Rice", "amount": 1000}, {"description": "Oil", "amount": 150}]}')
    vat_id = upload(('v.jpg', JPG + b'vatincl')).json()[0]['id']
    assert c.get(f'/documents/{vat_id}').json()['status'] == 'passed'
    qb_id = upload(('g2.jpg', JPG + b'good')).json()[0]['id']
    r = c.get('/export', params={'format': 'quickbooks'})
    qb = list(csv.reader(r.content.decode('utf-8-sig').splitlines()))
    assert qb[0][:3] == ['Bill no.', 'Supplier', 'Bill Date'] and int(r.headers['x-skipped']) >= 1
    first = [x for x in qb if x[0] == f'CC-{qb_id}']
    assert [(x[5], x[6]) for x in first] == [('Coffee', '3.00'), ('Lunch', '45.90'), ('Coke', '3.00'), ('Tax', '4.68')]
    assert [(x[5], x[6]) for x in qb if x[0] == 'GB1'] == [('Rice', '1000.00'), ('Oil', '150.00')]
    # the reviewed document whose total no longer matches its lines becomes a single line
    assert [(x[5], x[6]) for x in qb if x[0] == f'CC-{good_id}'] == [('Total', '60.00')]
    assert first[0][1:5] == ['Green Field', '05/26/2016', '05/26/2016', 'Uncategorized Expense']
    assert [(x[5], x[6]) for x in qb if x[1] == 'Round Co'] == [('Total', '1000.00')]

    # any-language file names download fine
    uni_id = upload(('領収書.jpg', JPG + b'good')).json()[0]['id']
    r = c.get(f'/documents/{uni_id}/file')
    assert r.status_code == 200 and "filename*=UTF-8''" in r.headers['content-disposition'] and r.content.startswith(JPG)

    # sign-in required on every endpoint; expired, wrong-audience and forged tokens are refused
    routes = [(m, rt.path.replace('{doc_id}', str(good_id)).replace('{n}', '0').replace('{vendor}', 'x'))
              for rt in app.app.routes if getattr(rt, 'endpoint', None) and rt.path.split('/')[1] not in ('docs', 'openapi.json', 'redoc')
              for m in rt.methods - {'HEAD'}]
    assert len(routes) == 19, routes
    anon = TestClient(app.app)
    for m, path in routes:
        assert anon.request(m, path).status_code == 401, (m, path)
    for bad in ({'exp': int(time.time()) - 60}, {'aud': 'anon'}, {'key': OTHER_KEY}):
        assert c.get('/documents', headers=as_user(ALICE, **bad)).status_code == 401, bad
    assert c.get('/documents', headers={'Authorization': 'Basic abc'}).status_code == 401
    assert c.get('/documents', headers=as_user(ALICE, iat=int(time.time()) + 5)).status_code == 200  # clock skew

    # the web app's origin may call the API from the browser; other sites may not
    pre = {'Access-Control-Request-Method': 'GET', 'Access-Control-Request-Headers': 'authorization'}
    assert anon.options('/documents', headers={'Origin': 'http://localhost:3000', **pre}).headers['access-control-allow-origin'] == 'http://localhost:3000'
    assert 'access-control-allow-origin' not in anon.options('/documents', headers={'Origin': 'https://evil.example', **pre}).headers
    # the browser may read an export's file name (else QuickBooks bills download as documents.csv)
    assert 'content-disposition' in c.get('/export', params={'format': 'quickbooks'}, headers={'Origin': 'http://localhost:3000'}).headers['access-control-expose-headers'].lower()

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

    # the webhook belongs to one account: another user's passed document is never sent
    sent = len(events)
    erin = as_user(str(uuid.uuid4()))
    passed = c.post('/documents', files=[('files', ('e.jpg', io.BytesIO(JPG + b'good'), 'image/jpeg'))], headers=erin).json()[0]
    assert c.get(f"/documents/{passed['id']}", headers=erin).json()['status'] == 'passed'
    assert c.delete(f"/documents/{passed['id']}", headers=erin).status_code == 204  # nor her deletes
    flush()
    assert len(events) == sent

    # refused uploads say why: not a supported type, or too large
    r = c.post('/documents', files=[('files', ('n.txt', io.BytesIO(b'hello'), 'text/plain'))], headers=erin).json()
    assert r[0]['error'] == 'Not a PDF, JPG, PNG, WebP or HEIC file.', r
    app.MAX_BYTES, real_max = 20, app.MAX_BYTES
    r = c.post('/documents', files=[('files', ('big.jpg', io.BytesIO(JPG + b'good' * 10), 'image/jpeg'))], headers=erin).json()
    app.MAX_BYTES = real_max
    assert r[0]['error'] == 'Larger than 10 MB.', r

    # daily upload limit per user: files over the limit are refused, then the whole request
    app.DAILY_UPLOAD_LIMIT = 2
    carol = as_user(CAROL)
    three = [('files', (f'{k}.jpg', io.BytesIO(JPG + b'good'), 'image/jpeg')) for k in range(3)]
    r = c.post('/documents', files=three, headers=carol).json()
    assert ['id' in x for x in r] == [True, True, False] and 'Daily limit' in r[2]['error']
    assert c.post('/documents', files=[('files', ('x.jpg', io.BytesIO(JPG + b'good'), 'image/jpeg'))], headers=carol).status_code == 429
    # deleting documents gives no quota back, and a retry counts as a read too
    for d in c.get('/documents', headers=carol).json():
        assert c.delete(f"/documents/{d['id']}", headers=carol).status_code == 204
    assert c.post('/documents', files=[('files', ('x.jpg', io.BytesIO(JPG + b'good'), 'image/jpeg'))], headers=carol).status_code == 429
    app.DAILY_UPLOAD_LIMIT = 3
    flagged = c.post('/documents', files=[('files', ('f.jpg', io.BytesIO(JPG + b'ambiguous'), 'image/jpeg'))], headers=carol).json()[0]['id']
    assert c.post(f'/documents/{flagged}/retry', headers=carol).status_code == 429
    assert c.get('/usage', headers=carol).json() == {'used': 3, 'limit': 3}  # shown on the upload page
    app.DAILY_UPLOAD_LIMIT = 50

    # delete account: everything of the user goes, other users keep theirs; a failed account removal keeps the data
    frank = as_user(FRANK := str(uuid.uuid4()))
    c.post('/documents', files=[('files', ('f.jpg', io.BytesIO(JPG + b'good'), 'image/jpeg'))], headers=frank)
    removed = []
    real_delete = app.delete_auth_user
    app.delete_auth_user = lambda uid: (_ for _ in ()).throw(RuntimeError('supabase down'))
    assert c.delete('/account', headers=frank).status_code == 502 and c.get('/stats', headers=frank).json()['documents'] == 1
    # a retry after Supabase already removed the account (its first answer lost) still counts as removed
    real_urlopen = urllib.request.urlopen
    def gone(*a, **k): raise urllib.error.HTTPError('u', 404, 'User not found', {}, None)
    urllib.request.urlopen, os.environ['SUPABASE_SECRET_KEY'] = gone, 'test-key'
    real_delete(FRANK)  # no exception
    urllib.request.urlopen = real_urlopen
    del os.environ['SUPABASE_SECRET_KEY']
    app.delete_auth_user = removed.append
    assert c.delete('/account', headers=frank).status_code == 204 and removed == [FRANK]
    assert c.get('/stats', headers=frank).json()['documents'] == 0 and c.get(f'/documents/{good_id}').status_code == 200

    # duplicates: a later copy of the same invoice (same vendor, number and total) is flagged and links to the first;
    # the first copy, the next invoice number and other users' copies are not
    george = as_user(str(uuid.uuid4()))
    ids = [x['id'] for x in c.post('/documents', headers=george, files=[
        ('files', (f'{k}.jpg', io.BytesIO(JPG + k.encode()), 'image/jpeg')) for k in ('inv1042', 'inv1042b', 'inv1043')]).json()]
    first, copy, other = (c.get(f'/documents/{i}', headers=george).json() for i in ids)
    assert first['status'] == 'passed' and other['status'] == 'passed', (first['checks'], other['checks'])
    assert copy['status'] == 'needs_review' and [x['check'] for x in copy['checks']] == ['duplicate']
    assert copy['checks'][0]['duplicate_of'] == ids[0] and 'INV-1042' in copy['checks'][0]['message']
    live = c.post('/check', json=copy['document'], params={'doc_id': ids[1]}, headers=george).json()['checks']
    assert [x['check'] for x in live] == ['duplicate']
    assert c.post('/check', json=first['document'], params={'doc_id': ids[0]}, headers=george).json()['checks'] == []
    assert c.post('/check', json=copy['document'], headers=as_user(str(uuid.uuid4()))).json()['checks'] == []

    # iPhone HEIC photos are stored as JPEG (model, viewer and browsers can read them); a fake HEIC is refused
    from PIL import Image
    heic = io.BytesIO()
    Image.new('RGB', (60, 40), 'white').save(heic, 'HEIF')
    ivy = as_user(str(uuid.uuid4()))
    r = c.post('/documents', headers=ivy, files=[('files', ('IMG_0001.HEIC', io.BytesIO(heic.getvalue()), 'image/heic')),
                                                  ('files', ('fake.heic', io.BytesIO(b'\x00\x00\x00\x18ftypheic' + b'x' * 50), 'image/heic'))]).json()
    assert heic.getvalue()[4:12] == b'ftypheic' and 'id' in r[0] and 'error' in r[1], r
    f = c.get(f'/documents/{r[0]["id"]}/file', headers=ivy)
    assert f.headers['content-type'] == 'image/jpeg' and f.content[:3] == b'\xff\xd8\xff'
    assert Image.open(io.BytesIO(f.content)).size == (60, 40)

    # delete removes the record and the file, and tells the webhook (the row gets marked deleted)
    assert c.delete(f'/documents/{good_id}').status_code == 204
    flush()
    e, sig, raw = events[-1]
    assert e == {'event': 'document.deleted', 'id': good_id, 'status': 'deleted', 'event_id': e['event_id']}
    assert sig == 'sha256=' + hmac.new(b'test-secret', raw, hashlib.sha256).hexdigest()
    assert c.get(f'/documents/{good_id}').status_code == 404 and c.get(f'/documents/{good_id}/file').status_code == 404
    assert c.delete(f'/documents/{good_id}').status_code == 404
    unread = upload(('u.jpg', JPG + b'boom')).json()[0]['id']  # failed: never had a spreadsheet row
    assert c.get(f'/documents/{unread}').json()['status'] == 'failed'
    flush()
    sent = len(events)
    assert c.delete(f'/documents/{unread}').status_code == 204
    flush()
    assert len(events) == sent  # so no deleted event
    assert c.post('/documents', files=[]).status_code in (400, 422)
    # size limits: an 11 MB file is refused; a request larger than 20 files x 10 MB is refused before reading
    over = c.post('/documents', files=[('files', ('big.jpg', io.BytesIO(JPG + b'0' * (10 * 1024 * 1024)), 'image/jpeg'))]).json()
    assert 'error' in over[0]
    assert c.post('/documents', content=b'x', headers={'content-length': str(300 * 1024 * 1024),
                                                       'content-type': 'multipart/form-data; boundary=x'}).status_code == 413
    assert c.post('/documents', files=[('files', (f'{k}.jpg', io.BytesIO(JPG + b'good'), 'image/jpeg')) for k in range(21)]).status_code == 400
    # errors a retry won't fix say so; exports keep exact numbers; XLSX only escapes '='
    assert app.public_error(RuntimeError('HTTP 400: image rejected')).startswith('The AI could not read this file')
    assert app.public_error(RuntimeError('HTTP 429: slow down')).startswith('The AI service is busy')
    assert app.public_error(RuntimeError('HTTP 400: API key not valid')) == 'Reading failed. Try again.'
    assert app.public_error(RuntimeError('HTTP 403: forbidden')) == 'Reading failed. Try again.'
    assert str(app.cell('total', app.Decimal('1E+1'))) == '10'
    assert str(app.cell('total', 12.5)) == '12.5' and str(app.cell('total', app.Decimal('12.50'))) == '12.50'
    assert app.cell('vendor', '- Discount', xlsx=True) == '- Discount' and app.cell('vendor', '- Discount') == "'- Discount"
    assert app.cell('vendor', '=1+1', xlsx=True) == "'=1+1"

    # a user's own webhook address (Account page)
    judy = as_user(JUDY := str(uuid.uuid4()))
    own_url = f'http://127.0.0.1:{hook.server_port}/own'
    assert c.get('/account/webhook', headers=judy).json() == {'enabled': False, 'url': None, 'last_at': None, 'last_error': None}
    assert c.put('/account/webhook', json={'url': own_url}, headers=judy).status_code == 503  # no WEBHOOK_KEY on this server
    os.environ['WEBHOOK_KEY'] = 'test-webhook-key'
    # only https addresses on the public internet: never this server's own network
    for bad in ('http://example.com/hook', 'ftp://example.com/x', 'https://127.0.0.1/x', 'https://localhost/x', 'https://10.0.0.5/x',
                'https://192.168.1.1/x', 'https://169.254.169.254/latest/meta-data', 'https://[::1]/x', 'https://[::ffff:127.0.0.1]/x',
                'https://100.64.0.1/x', 'https://0.0.0.0/x', 'https://no-such-host.invalid/x', 'https://example.com:99999/x', own_url):
        assert c.put('/account/webhook', json={'url': bad}, headers=judy).status_code == 400, bad
        assert not app.public_url(bad), bad
    assert app.public_url('https://8.8.8.8/hook') and not app.public_url('https://user:pw@8.8.8.8/hook')
    # checked again when sending, redirects are never followed, and a whole send takes at most `timeout` seconds
    started = time.monotonic()
    for url, own in (('https://127.0.0.1/x', True), (f'http://127.0.0.1:{hook.server_port}/redirect', False),
                     (f'http://127.0.0.1:{hook.server_port}/drip', False)):
        try:
            app.open_webhook(url, {'event': 'x', 'id': None}, 's', own, 1)
            raise AssertionError(url)
        except (ValueError, RuntimeError, OSError, http.client.HTTPException):
            pass
    assert time.monotonic() - started < 3 and not any(e['event'] == 'x' for e, _, _ in events)
    # the local receiver stands in for a public address; sending connects to the IP that was checked,
    # so a name that would resolve elsewhere (here: nowhere) can't change where the request goes
    pinned = f'http://pinned.invalid:{hook.server_port}/own'
    real_public_ip, app.public_ip = app.public_ip, lambda url: '127.0.0.1' if url in (own_url, pinned) else None
    assert app.open_webhook(pinned, {'event': 'pinned', 'id': None}, 's', True, 5) == 200
    assert own_events[-1][0]['event'] == 'pinned'
    saved = c.put('/account/webhook', json={'url': f' {own_url} '}, headers=judy).json()
    secret = saved['secret']
    shown = c.get('/account/webhook', headers=judy).json()
    assert saved['url'] == shown['url'] == own_url and shown['enabled'] and secret not in str(shown)  # the secret is shown once only
    with store.conn() as con:
        stored = con.execute('SELECT url, secret FROM webhooks WHERE user_id = %s', (JUDY,)).fetchone()
    assert '127.0.0.1' not in stored['url'] and secret not in stored['secret']  # encrypted in the database
    tested = c.post('/account/webhook/test', headers=judy).json()
    assert tested == {'ok': True, 'status': 200} and own_events[-1][0] == {'event': 'test', 'id': None}
    assert c.post('/account/webhook/test', headers=judy).status_code == 429  # one test every 10 s
    # WEBHOOK_KEY changed: the address can't be read any more, and the Account page says so
    os.environ['WEBHOOK_KEY'] = 'another-key'
    gone = c.get('/account/webhook', headers=judy).json()
    assert gone['url'] is None and 'Save it again' in gone['last_error']
    os.environ['WEBHOOK_KEY'] = 'test-webhook-key'
    assert c.post('/account/webhook/test', headers=bob).status_code == 404

    # her documents go to her address, signed with her secret; the server's n8n never sees them
    sent = len(events)
    judy_doc = c.post('/documents', files=[('files', ('j.jpg', io.BytesIO(JPG + b'good'), 'image/jpeg'))], headers=judy).json()[0]['id']
    flush()
    e, sig, raw = own_events[-1]
    assert e['event'] == 'document.passed' and e['id'] == judy_doc and len(events) == sent
    assert sig == 'sha256=' + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    assert all(ev['id'] == judy_doc or ev['event'] in ('test', 'pinned') for ev, _, _ in own_events)  # nobody else's documents
    # a failed event insert never undoes the document change (savepoint)
    with store.conn() as con:
        con.execute('ALTER TABLE webhook_events RENAME TO webhook_events_off')
    kept = c.post('/documents', files=[('files', ('k.jpg', io.BytesIO(JPG + b'good'), 'image/jpeg'))], headers=judy).json()[0]['id']
    with store.conn() as con:
        con.execute('ALTER TABLE webhook_events_off RENAME TO webhook_events')
        assert not con.execute("SELECT 1 FROM webhook_events WHERE payload->>'id' = %s", (str(kept),)).fetchone()
    assert c.get(f'/documents/{kept}', headers=judy).json()['status'] == 'passed'
    flush()
    # WEBHOOK_KEY missing after a deploy: events wait in the table instead of being dropped, and go once it is back
    del os.environ['WEBHOOK_KEY']
    waiting = c.post('/documents', files=[('files', ('w.jpg', io.BytesIO(JPG + b'good'), 'image/jpeg'))], headers=judy).json()[0]['id']
    flush()
    with store.conn() as con:
        assert con.execute("SELECT attempts FROM webhook_events WHERE payload->>'id' = %s", (str(waiting),)).fetchone()['attempts'] == 1
        os.environ['WEBHOOK_KEY'] = 'test-webhook-key'
        con.execute('UPDATE webhook_events SET next_at = now()')
    flush()
    assert own_events[-1][0]['id'] == waiting
    # a failed send is retried; after the last retry it is dropped, the error is shown, and the next event still goes
    real_retry, app.RETRY_SECONDS = app.RETRY_SECONDS, (0,)
    Hook.fail = 1
    assert c.delete(f'/documents/{judy_doc}', headers=judy).status_code == 204
    flush()
    assert own_events[-1][0]['event'] == 'document.deleted' and c.get('/account/webhook', headers=judy).json()['last_error'] is None
    Hook.fail = 2
    lost = c.post('/documents', files=[('files', ('j.jpg', io.BytesIO(JPG + b'good'), 'image/jpeg'))], headers=judy).json()[0]['id']
    flush()
    assert own_events[-1][0]['id'] != lost and '500' in c.get('/account/webhook', headers=judy).json()['last_error']
    nxt = c.post('/documents', files=[('files', ('j.jpg', io.BytesIO(JPG + b'good'), 'image/jpeg'))], headers=judy).json()[0]['id']
    flush()
    assert own_events[-1][0]['id'] == nxt and c.get('/account/webhook', headers=judy).json()['last_error'] is None
    app.RETRY_SECONDS = real_retry
    # a slow address delays only its own user
    Hook.slow, arrived[:] = 3, []
    c.post('/documents', files=[('files', ('j.jpg', io.BytesIO(JPG + b'good'), 'image/jpeg'))], headers=judy)
    app.WAKE.set(); time.sleep(0.3)  # Judy's event is on its way
    c.post('/documents', files=[('files', ('a.jpg', io.BytesIO(JPG + b'good'), 'image/jpeg'))])
    flush()
    assert arrived == ['/hook', '/own'], arrived
    Hook.slow = 0
    # removing the address stops events; deleting the account removes the address
    assert c.delete('/account/webhook', headers=judy).status_code == 204
    assert c.get('/account/webhook', headers=judy).json()['url'] is None
    c.put('/account/webhook', json={'url': own_url}, headers=judy)
    assert c.delete('/account', headers=judy).status_code == 204
    with store.conn() as con:
        assert con.execute('SELECT count(*) AS n FROM webhooks WHERE user_id = %s', (JUDY,)).fetchone()['n'] == 0
    app.public_ip = real_public_ip
    # second reading: a flagged document is read again by a second model; nothing about the document changes
    erin = as_user(str(uuid.uuid4()))
    def second_of(doc_id):
        with store.conn() as con:
            return con.execute('SELECT second_reading, second_read_at, extracted, document, status, checks FROM documents WHERE id = %s',
                               (doc_id,)).fetchone()
    memo_id = c.post('/documents', files=[('files', ('m.jpg', io.BytesIO(JPG + b'memo'), 'image/jpeg'))], headers=erin).json()[0]['id']
    second_done()
    row = second_of(memo_id)
    assert row['status'] == 'needs_review' and row['second_read_at'] is not None
    assert row['second_reading']['items'][1]['amount'] == '240' and row['second_reading']['issue_date'] == '2024-05-20'
    assert row['document'] == row['extracted'] and row['document']['items'][1]['amount'] == '280'  # untouched
    # the second_reading check shows as soon as the reading is in, with no edit needed
    assert any(ck['check'] == 'second_reading' for ck in row['checks']), row['checks']
    assert c.get(f'/documents/{memo_id}', headers=erin).json()['second_read'] is True
    # passed, and flagged only for the date question: no second reading
    passed_id = c.post('/documents', files=[('files', ('g.jpg', io.BytesIO(JPG + b'good'), 'image/jpeg'))], headers=erin).json()[0]['id']
    date_id = c.post('/documents', files=[('files', ('a.jpg', io.BytesIO(JPG + b'ambiguous2'), 'image/jpeg'))], headers=erin).json()[0]['id']
    second_done()
    # passed documents now get a second reading too, from leftover quota (same answer as the first, so it stays passed)
    assert second_of(passed_id)['second_read_at'] is not None and second_of(date_id)['second_read_at'] is None
    # date_id never got a second reading (only date_ambiguous, excluded): second_read says so
    assert c.get(f'/documents/{date_id}', headers=erin).json()['second_read'] is False
    # the differences, field by field; a date comes with its printed text
    d = c.get(f'/documents/{memo_id}', headers=erin).json()
    assert {(x['field'], x['from'], x['to']) for x in d['second_reading']} == {('items[1].amount', '280', '240'), ('issue_date', '2024-06-20', '2024-05-20')}, d['second_reading']
    assert [x['text'] for x in d['second_reading'] if x['field'] == 'issue_date'] == ['20/05/2024']
    # a value the user already took drops off; other documents' readings are not shown
    edited = {**d['document'], 'items': [*d['document']['items'][:1], {**d['document']['items'][1], 'amount': '240.00'}, d['document']['items'][2]]}
    left = c.post('/check', json=edited, params={'doc_id': memo_id}, headers=erin).json()['second_reading']
    assert [x['field'] for x in left] == ['issue_date'], left
    assert c.post('/check', json=edited, params={'doc_id': memo_id}).json()['second_reading'] == []  # Alice: not her document
    assert c.get(f'/documents/{passed_id}', headers=erin).json()['second_reading'] == []
    # once reviewed, /check no longer offers the second reading for it (GET already stops: status != needs_review)
    c.put(f'/documents/{memo_id}', json=edited, headers=erin)
    assert c.post('/check', json=edited, params={'doc_id': memo_id}, headers=erin).json()['second_reading'] == []
    # a different number of lines: one change that replaces the list
    four_id = c.post('/documents', files=[('files', ('m4.jpg', io.BytesIO(JPG + b'memo4'), 'image/jpeg'))], headers=erin).json()[0]['id']
    second_done()
    changes = c.get(f'/documents/{four_id}', headers=erin).json()['second_reading']
    assert [x['field'] for x in changes] == ['items'] and len(changes[0]['to']) == 4 and changes[0]['from'] == '3 lines'
    # the quota runs out: the document is untouched, the attempt counts toward the cap
    q_id = c.post('/documents', files=[('files', ('q.jpg', io.BytesIO(JPG + b'memoq'), 'image/jpeg'))], headers=erin).json()[0]['id']
    second_done()
    row = second_of(q_id)
    assert row['second_read_at'] is not None and row['second_reading'] is None and row['status'] == 'needs_review'
    # the daily cap (whole app) stops further second readings
    real_cap = app.SECOND_READ_DAILY_LIMIT
    with store.conn() as con:
        app.SECOND_READ_DAILY_LIMIT = con.execute("SELECT count(*) AS n FROM second_reads WHERE at > now() - interval '24 hours'").fetchone()['n']
    capped = c.post('/documents', files=[('files', ('m2.jpg', io.BytesIO(JPG + b'memo'), 'image/jpeg'))], headers=erin).json()[0]['id']
    second_done()
    assert second_of(capped)['second_read_at'] is None
    assert c.get(f'/documents/{capped}', headers=erin).json()['second_read'] is False  # capped: no reading, so no false tick
    app.SECOND_READ_DAILY_LIMIT = real_cap
    # retry keeps the first second reading: it read the same file blind, so it is still valid
    before = second_of(memo_id)
    with store.conn() as con:
        con.execute("UPDATE documents SET status = 'failed' WHERE id = %s", (memo_id,))
    assert c.post(f'/documents/{memo_id}/retry', headers=erin).status_code == 202
    second_done()
    after = second_of(memo_id)
    assert after['second_read_at'] == before['second_read_at'] and after['second_reading'] == before['second_reading']
    # dates are compared after the vendor's saved date order: same printed text, read the other way, is not a change
    c.put('/vendors/Datevendor/date-order', json={'date_order': 'DMY'}, headers=erin)
    dateamb_id = c.post('/documents', files=[('files', ('d.jpg', io.BytesIO(JPG + b'dateamb'), 'image/jpeg'))], headers=erin).json()[0]['id']
    second_done()
    d = c.get(f'/documents/{dateamb_id}', headers=erin).json()
    assert d['status'] == 'needs_review' and 'issue_date' not in {x['field'] for x in d['second_reading']}, d['second_reading']

    # a passed receipt whose second reading meaningfully differs (total) moves to needs_review with a new check;
    # Alice's documents go to the server's webhook (WEBHOOK_USER_ID), so the event can be checked directly
    pass2_id = c.post('/documents', files=[('files', ('p2.jpg', io.BytesIO(JPG + b'pass2'), 'image/jpeg'))]).json()[0]['id']
    second_done()
    row = second_of(pass2_id)
    assert row['status'] == 'needs_review'
    assert {ck['check'] for ck in row['checks']} == {'second_reading'}, row['checks']
    assert row['document'] == row['extracted']  # the AI's reading and the user's document are never touched
    flush()
    e, _, _ = events[-1]
    assert e['id'] == pass2_id and e['event'] == 'document.needs_review'
    # the check is live: applying the second reading's total makes it pass again
    d2 = c.get(f'/documents/{pass2_id}').json()
    fixed = {**d2['document'], 'total': '120'}
    assert not any(x['check'] == 'second_reading' for x in c.post('/check', json=fixed, params={'doc_id': pass2_id}).json()['checks'])
    # a passed receipt whose second reading differs only in vendor case and a 0.00 line stays passed
    pass3_id = c.post('/documents', files=[('files', ('p3.jpg', io.BytesIO(JPG + b'pass3'), 'image/jpeg'))]).json()[0]['id']
    second_done()
    row3 = second_of(pass3_id)
    assert row3['second_read_at'] is not None and row3['status'] == 'passed'  # a reading ran; it just wasn't meaningful

    # per-user cap: a user who already used today's personal quota gets no more second readings, another user still does
    with store.conn() as con:
        alice_used = con.execute("SELECT count(*) AS n FROM second_reads WHERE user_id = %s AND at > now() - interval '24 hours'",
                                 (ALICE,)).fetchone()['n']
    real_per_user, app.SECOND_READ_PER_USER = app.SECOND_READ_PER_USER, alice_used
    alice_flagged = c.post('/documents', files=[('files', ('af.jpg', io.BytesIO(JPG + b'memo'), 'image/jpeg'))]).json()[0]['id']
    bob_flagged = c.post('/documents', files=[('files', ('bf.jpg', io.BytesIO(JPG + b'memo'), 'image/jpeg'))], headers=bob).json()[0]['id']
    second_done()
    assert second_of(alice_flagged)['second_read_at'] is None
    assert second_of(bob_flagged)['second_read_at'] is not None
    app.SECOND_READ_PER_USER = real_per_user

    # leftover rule: passed documents use only quota beyond SECOND_READ_FLAGGED_RESERVE; flagged ones still get theirs
    with store.conn() as con:
        used = con.execute("SELECT count(*) AS n FROM second_reads WHERE at > now() - interval '24 hours'").fetchone()['n']
    real_cap2, app.SECOND_READ_DAILY_LIMIT = app.SECOND_READ_DAILY_LIMIT, used + app.SECOND_READ_FLAGGED_RESERVE
    grace = as_user(str(uuid.uuid4()))
    no_second_id = c.post('/documents', files=[('files', ('np.jpg', io.BytesIO(JPG + b'good'), 'image/jpeg'))], headers=grace).json()[0]['id']
    still_flagged_id = c.post('/documents', files=[('files', ('sf.jpg', io.BytesIO(JPG + b'memo'), 'image/jpeg'))], headers=grace).json()[0]['id']
    second_done()
    assert second_of(no_second_id)['second_read_at'] is None
    assert second_of(still_flagged_id)['second_read_at'] is not None
    app.SECOND_READ_DAILY_LIMIT = real_cap2

    # deleting a document does not give second-reading quota back
    frank = as_user(str(uuid.uuid4()))
    real_per_user2, app.SECOND_READ_PER_USER = app.SECOND_READ_PER_USER, 1
    gone_id = c.post('/documents', files=[('files', ('f1.jpg', io.BytesIO(JPG + b'memo'), 'image/jpeg'))], headers=frank).json()[0]['id']
    second_done()
    assert second_of(gone_id)['second_read_at'] is not None
    assert c.delete(f'/documents/{gone_id}', headers=frank).status_code == 204
    again_id = c.post('/documents', files=[('files', ('f2.jpg', io.BytesIO(JPG + b'memo'), 'image/jpeg'))], headers=frank).json()[0]['id']
    second_done()
    assert second_of(again_id)['second_read_at'] is None
    app.SECOND_READ_PER_USER = real_per_user2

    # the same lines in another order are no difference; a real one still is
    two = app.Document(items=[{'amount': '10'}, {'amount': '20'}])
    assert app.second_reading_changes(two, app.Document(items=[{'amount': '20.00'}, {'amount': '10'}])) == []
    changed = app.second_reading_changes(two, app.Document(items=[{'amount': '20'}, {'amount': '11'}]))
    assert [x['field'] for x in changed] == ['items[0].amount', 'items[1].amount'], changed

    # a race: the document is re-saved (e.g. a vendor date-order re-check) while the second model call is
    # in flight; second_read must decide on the document as it is now, not as it was before the call
    race_id = c.post('/documents', files=[('files', ('rc.jpg', io.BytesIO(JPG + b'race'), 'image/jpeg'))], headers=erin).json()[0]['id']
    second_done()
    race_row = second_of(race_id)
    assert race_row['status'] == 'needs_review'
    assert race_row['document']['items'][0]['amount'] == '100'  # the concurrent fix; second_read never touches document
    # on the fixed document, items_sum now passes; only the (stale) second reading still disagrees with the fix
    assert {ck['check'] for ck in race_row['checks']} == {'second_reading'}, race_row['checks']
    print('ok')
finally:
    import store
    with store.conn() as con:
        con.execute(f'DROP SCHEMA {store.schema_name()} CASCADE')
