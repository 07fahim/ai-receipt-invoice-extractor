import os
import time
import uuid

os.environ['APP_SCHEMA'] = 'test_' + uuid.uuid4().hex[:8]

import providers

os.environ['GROQ_API_KEY'] = 'test-groq'
os.environ['OPENROUTER_API_KEY'] = 'test-or'


def chat_fallback():
    real, seen = providers.post, []

    def fake(url, headers, body, retries=3, timeout=60):
        seen.append((url, body['model'], retries, timeout))
        if 'groq' in url:
            raise RuntimeError('HTTP 429: rate limit')
        return {'choices': [{'message': {'role': 'assistant', 'content': 'hi'}}], 'usage': {'total_tokens': 7}}, 1

    providers.post = fake
    try:
        msg, usage = providers.chat([{'role': 'user', 'content': 'x'}], [])
        assert msg['content'] == 'hi' and usage == {'total_tokens': 7}
        assert [s[1] for s in seen] == ['qwen/qwen3.8-27b', 'qwen/qwen3.8-27b:free'], seen
        assert all(s[2] == 0 and s[3] == 20 for s in seen)  # no waiting retries: the fallback is the retry

        def down(*a, **k):
            raise RuntimeError('HTTP 503')
        providers.post = down
        try:
            providers.chat([{'role': 'user', 'content': 'x'}], [])
            raise AssertionError('expected RuntimeError')
        except RuntimeError as e:
            assert 'qwen/qwen3.8-27b' in str(e)
    finally:
        providers.post = real


from datetime import date, timedelta
import json

import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from psycopg.types.json import Jsonb

import app
import assistant
import store

os.environ['SUPABASE_URL'] = 'https://test.supabase.co'
KEY = ec.generate_private_key(ec.SECP256R1())
app.signing_key = lambda token: KEY.public_key()
app.delete_auth_user = lambda uid: None
ALICE, BOB = str(uuid.uuid4()), str(uuid.uuid4())


def as_user(sub):
    body = {'sub': sub, 'aud': 'authenticated', 'iss': 'https://test.supabase.co/auth/v1', 'exp': int(time.time()) + 3600}
    return {'Authorization': 'Bearer ' + jwt.encode(body, KEY, algorithm='ES256')}


def add(uid, status, checks=None, **fields):
    doc = app.Document(**fields)
    with store.conn() as con:
        return con.execute(
            'INSERT INTO documents (user_id, file_name, mime, file, status, document, checks, vendor, currency, issue_date, total) '
            "VALUES (%s, 'x.jpg', 'image/jpeg', %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (uid, b'\x00', status, Jsonb(doc.model_dump(mode='json')), Jsonb(checks or []), doc.vendor, doc.currency,
             doc.issue_date, doc.total)).fetchone()['id']


def tool(uid, name, **args):
    with store.conn() as con:
        return json.loads(assistant.run_tool(con, uid, name, args))


def tools():
    soon = (date.today() + timedelta(days=3)).isoformat()
    s1 = add(ALICE, 'passed', vendor='Shwapno', currency='BDT', issue_date='2026-09-03', total=1200,
             items=[{'description': 'Rice 5kg', 'amount': 1200}])
    s2 = add(ALICE, 'reviewed', vendor='SHWAPNO', currency='BDT', issue_date='2026-09-20', total=800,
             items=[{'description': 'Milk', 'amount': 800}])
    add(ALICE, 'passed', vendor='Aarong', currency='BDT', issue_date='2026-08-10', total=6200)
    flagged = add(ALICE, 'needs_review', checks=[{'check': 'items_sum', 'fields': ['items', 'subtotal'],
                                                  'message': 'Line items add up to 90. The subtotal is 100.'}],
                  vendor='Shwapno', currency='BDT', issue_date='2026-09-25', subtotal=100, total=100,
                  items=[{'description': 'Eggs', 'amount': 90}])
    latte = add(ALICE, 'passed', vendor='Starbucks', currency='USD', issue_date='2026-09-05', total=5.5,
                items=[{'description': 'Caffe Latte', 'amount': 5.5}])
    bill = add(ALICE, 'passed', vendor='Acme Supplies', currency='USD', issue_date='2026-09-28', due_date=soon, total=100)
    bob = add(BOB, 'passed', vendor='Shwapno', currency='BDT', issue_date='2026-09-05', total=9999,
              items=[{'description': 'Caffe Latte', 'amount': 9999}])

    found = tool(ALICE, 'search_documents', vendor='shwapno')
    assert sorted(d['id'] for d in found) == sorted([s1, s2, flagged]), found  # all statuses, never Bob's
    assert tool(BOB, 'search_documents', vendor='shwapno')[0]['id'] == bob

    sep = tool(ALICE, 'spend_summary', group_by='vendor', date_from='2026-09-01', date_to='2026-09-30')
    shw = [r for r in sep if r['vendor'].lower().startswith('shwapno')]
    assert len(shw) == 1 and float(shw[0]['total']) == 2000 and shw[0]['n'] == 2, sep  # 'SHWAPNO' groups with 'Shwapno' (letter case only, like /stats); flagged left out
    # same numbers as the dashboard
    from fastapi.testclient import TestClient
    stats = TestClient(app.app).get('/stats', headers=as_user(ALICE)).json()
    mine = {(r['currency'], float(r['total'])) for r in tool(ALICE, 'spend_summary', group_by='currency')}
    assert mine == {(r['currency'], float(r['total'])) for r in stats['spend_by_currency']}, (mine, stats)

    doc = tool(ALICE, 'get_document', id=flagged)
    assert doc['checks'][0]['message'].startswith('Line items add up to 90'), doc
    assert 'error' in tool(ALICE, 'get_document', id=bob)  # Bob's document is "not found" for Alice

    assert [d['id'] for d in tool(ALICE, 'due_bills', days=7)] == [bill]
    hits = tool(ALICE, 'search_items', text='latte')
    assert [d['id'] for d in hits] == [latte] and hits[0]['matches'] == ['Caffe Latte'], hits
    assert tool(ALICE, 'search_items', text='100%') == []  # % is a plain character, not a wildcard

    for name, args in [('drop_tables', {}), ('spend_summary', {'group_by': 'user_id'}),
                       ('search_documents', {'date_from': 'last week'}), ('due_bills', {'days': 500}),
                       ('get_document', {})]:
        assert 'error' in tool(ALICE, name, **args), name
    with store.conn() as con:
        assert 'error' in json.loads(assistant.run_tool(con, ALICE, 'search_documents', None))  # arguments that were not JSON
    return {'shwapno': (s1, s2), 'flagged': flagged}


try:
    chat_fallback()
    seeded = tools()
    print('ok')
finally:
    with store.conn() as con:
        con.execute(f'DROP SCHEMA {store.schema_name()} CASCADE')
