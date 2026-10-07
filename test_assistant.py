import os
import re
import time
import uuid

os.environ['APP_SCHEMA'] = 'test_' + uuid.uuid4().hex[:8]

import providers

os.environ['GEMINI_API_KEY'] = 'test-gemini'
os.environ['GROQ_API_KEY'] = 'test-groq'
os.environ['OPENROUTER_API_KEY'] = 'test-or'


def chat_fallback():
    real, seen = providers.post, []

    def fake(url, headers, body, retries=3, timeout=60):
        seen.append((url, body['model'], retries, timeout))
        assert body['max_tokens'] == 800  # Groq refuses requests that could pass 1,000 output tokens a minute
        if 'groq' in url or 'googleapis' in url:
            raise RuntimeError('HTTP 429: rate limit')
        return {'choices': [{'message': {'role': 'assistant', 'content': 'hi'}}], 'usage': {'total_tokens': 7}}, 1

    providers.post = fake
    try:
        msg, usage = providers.chat([{'role': 'user', 'content': 'x'}], [])
        assert msg['content'] == 'hi' and usage == {'total_tokens': 7}
        assert [s[1] for s in seen] == ['gemini-3.5-flash-lite', 'qwen/qwen3.8-27b', 'openrouter/free'], seen
        assert all(s[2] == 0 and s[3] == 20 for s in seen)  # no waiting retries: the fallback is the retry

        def down(*a, **k):
            raise RuntimeError('HTTP 503')
        providers.post = down
        try:
            providers.chat([{'role': 'user', 'content': 'x'}], [])
            raise AssertionError('expected RuntimeError')
        except RuntimeError as e:
            assert 'gemini-3.5-flash-lite' in str(e) and 'qwen/qwen3.8-27b' in str(e)
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
ALICE, BOB, CARL = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())


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
    assert shw[0]['total'] == '2000.00', shw  # money columns go to the model with 2 decimals, not Decimal's 6
    # same numbers as the dashboard
    from fastapi.testclient import TestClient
    stats = TestClient(app.app).get('/stats', headers=as_user(ALICE)).json()
    mine = {(r['currency'], float(r['total'])) for r in tool(ALICE, 'spend_summary', group_by='currency')}
    assert mine == {(r['currency'], float(r['total'])) for r in stats['spend_by_currency']}, (mine, stats)

    doc = tool(ALICE, 'get_document', id=flagged)
    assert doc['checks'][0]['message'] == "In the AI's reading: Line items add up to 90. The subtotal is 100.", doc
    assert 'error' in tool(ALICE, 'get_document', id=bob)  # Bob's document is "not found" for Alice

    # a Bangla question gets Bangla check messages: one example of every check message in validate.py and app.py
    with store.conn() as con:
        in_bangla = json.loads(assistant.run_tool(con, ALICE, 'get_document', {'id': flagged}, True))
        model_says_bangla = json.loads(assistant.run_tool(con, ALICE, 'get_document', {'id': flagged, 'in_bangla': True}))
    assert in_bangla['checks'][0]['message'] == 'এআই-এর পড়া অনুযায়ী: লাইন আইটেমগুলোর যোগফল 90। সাবটোটাল 100।', in_bangla
    assert model_says_bangla['checks'][0]['message'].startswith("In the AI's reading"), model_says_bangla  # the app decides
    examples = ["This doesn't look like a receipt or invoice.", 'Is 9/1/2016 day first or month first?',
                'This file seems to hold 2 documents. Upload one per file.', 'No total found.',
                'The total is printed as 1.234. Is it 1,234?', 'There are amounts but no line items.',
                'Line items add up to 90. The subtotal is 100.', 'Subtotal + tax + service - discount = 59.11. The total is 64.43.',
                'Line items add up to 90. The total is 100.', '2 x 120 = 240. The line says 280.',
                'The issue date 2027-01-01 is in the future.', 'The due date is before the issue date.',
                '"XYZ" is not a currency code.', 'Same vendor, number and total as 001. It was uploaded earlier.',
                'A second AI reading differs. Compare with the photo.',
                'The amounts look 1,000 times too small. The total would be 64,430.',
                'আম: is the quantity 1.89? Then the line adds up.',
                'Did you mean 8.50 instead of 85.0? Then every sum adds up.',
                'VAT 15% of 851.20 is 127.68. The document says 120.',
                'GST 5% of 1,000 is 50. The document says 60.',
                'Tax 8.5% of 80.44 is at most 6.84. The document says 8.55.',
                '10% of 26.85 is 2.69. The discount is 3.49.',
                'GB123 4567 89 is not a valid UK VAT number. Check it on the document.',
                '07AAHCA1234F1Z6 is not a valid GSTIN. Check it on the document.',
                'No seller VAT number found. It is needed to claim this VAT back.',
                'No seller GSTIN found. It is needed to claim this GST back.',
                'This document is dated 01/2024. The rest of this upload is from 03/2026.']
    assert len(examples) == len(assistant.BANGLA)
    # a new check or fix-suggestion message needs a Bangla pattern in assistant.BANGLA and an example here:
    # 18 checks, 3 suggestions (2 found.append, 1 direct return), 1 note dict in validate.py
    src, app_src = open('validate.py', encoding='utf-8').read(), open('app.py', encoding='utf-8').read()
    assert (src.count("fail('"), src.count('found.append('), src.count("{'message': f'"), app_src.count("'message': "))         == (18, 2, 2, 2), 'a message was added or removed: update assistant.BANGLA and the examples above'
    for m in examples:
        assert not re.search('[A-Za-z]{3}', assistant.bangla(m).replace('XYZ', '').replace('AI', '').replace('07AAHCA1234F1Z6', '')), m
    assert assistant.bangla('Something new.') == 'Something new.'  # no match: stays English

    # an ambiguous date: both readings given, no internal check code or status, like the Taco Bell case
    ambiguous = add(ALICE, 'needs_review', checks=[{'check': 'date_ambiguous', 'fields': ['issue_date'],
                                                    'message': 'Is 9/1/2016 day first or month first?'}],
                    vendor='Taco Bell', currency='USD', issue_date='2016-09-01', issue_date_text='9/1/2016', total=5)
    amb = tool(ALICE, 'get_document', id=ambiguous)
    check = amb['checks'][0]
    assert check['fields'] == ['issue date'], check  # no underscore
    assert check['readings'] == ['1 Sep 2016 (month first)', '9 Jan 2016 (day first)'], check
    dump = json.dumps(amb)
    assert 'date_ambiguous' not in dump and 'needs_review' not in dump, dump

    # a note check (level note) is marked note so the chat model doesn't read it as a failure; a normal check isn't
    note_check = assistant.plain_check(None, {'check': 'tax_id_missing', 'fields': ['seller_tax_id'],
                                              'message': 'No seller VAT number found.', 'level': 'note'})
    assert note_check.get('note') is True, note_check
    plain = assistant.plain_check(None, {'check': 'total_present', 'fields': ['total'], 'message': 'No total found.'})
    assert 'note' not in plain, plain

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
    all_alice = tool(ALICE, 'search_documents', vendor='', status=None)  # empty/None optional args are dropped, not filtered on
    assert len(all_alice) == 7, all_alice
    assert 'error' in tool(ALICE, 'search_items', text='a\x00b')  # NUL byte: psycopg.DataError, not a crash

    # a tool error that Postgres itself raises (not the client) must still leave the connection usable:
    # a bad stored due_date makes the ::date cast in due_bills fail server-side (InvalidDatetimeFormat, a
    # psycopg.DataError subclass), aborting the transaction; run_tool must roll back so the same connection
    # still works for the next call. A throwaway user keeps this out of Alice's counts above.
    carl_doc = add(CARL, 'passed', vendor='Bad Co', currency='BDT', issue_date='2026-09-01', due_date='2026-09-10', total=10)
    with store.conn() as con:
        con.execute("UPDATE documents SET document = jsonb_set(document, '{due_date}', '\"2026-13-45\"') WHERE id = %s",
                    (carl_doc,))
    with store.conn() as con:
        error_result = json.loads(assistant.run_tool(con, CARL, 'due_bills', {'days': 7}))
        assert 'error' in error_result, error_result
        working_result = json.loads(assistant.run_tool(con, CARL, 'search_documents', {}))
        assert isinstance(working_result, list) and any(d['id'] == carl_doc for d in working_result), working_result
    return {'shwapno': (s1, s2), 'flagged': flagged}


def loop(seeded):
    real, sent = providers.chat, []

    def script(*replies):
        queue = list(replies)

        def fake(messages, tools, tool_choice='auto'):
            sent.append((messages, tool_choice))
            return queue.pop(0) if queue else ({'content': 'done'}, {'total_tokens': 1})
        providers.chat = fake

    call = lambda name, args, n=1: {'tool_calls': [{'id': f'c{n}', 'type': 'function',
                                                    'function': {'name': name, 'arguments': json.dumps(args)}}]}
    try:
        # one tool round, then the answer; <think> blocks are removed
        script((call('spend_summary', {'group_by': 'vendor', 'date_from': '2026-09-01'}), {'total_tokens': 300}),
               ({'content': '<think>sum it</think>You spent 2,000 BDT at Shwapno.'}, {'total_tokens': 400}))
        out = assistant.answer(ALICE, [{'role': 'user', 'content': 'hi'}, {'role': 'assistant', 'content': 'Hello.'}],
                               'How much at Shwapno in September?', '/app/documents/%d' % seeded['flagged'], seeded['flagged'])
        assert out['reply'] == 'You spent 2,000 BDT at Shwapno.' and out['tokens'] == 700, out
        assert out['steps'] == ['Summed spend by vendor'], out
        first = sent[0][0]
        assert first[0]['role'] == 'system' and f'#{seeded["flagged"]}' in first[0]['content']  # knows the open document
        assert [m['role'] for m in first[1:]] == ['user', 'assistant', 'user']
        tool_msg = sent[1][0][-1]
        assert tool_msg['role'] == 'tool' and tool_msg['tool_call_id'] == 'c1' and '2000' in tool_msg['content']

        # Gemini needs its thought signature sent back with the tool call
        sent.clear(); signed = call('due_bills', {'days': 7})
        signed['tool_calls'][0]['extra_content'] = {'google': {'thought_signature': 'sig'}}
        script((signed, {}), ({'content': 'ok'}, {}))
        assistant.answer(ALICE, [], 'due?')
        assert sent[1][0][-2]['tool_calls'][0]['extra_content'] == {'google': {'thought_signature': 'sig'}}

        # a Bangla question gets the note to write the whole reply, check messages too, in Bangla; English does not
        assert 'wrote in Bangla' not in first[0]['content']
        sent.clear(); script(({'content': 'ok'}, {}))
        assistant.answer(ALICE, [], 'এই রসিদে সমস্যা কী?')
        assert 'wrote in Bangla' in sent[0][0][0]['content']

        # someone else's document id from the page is not mentioned
        sent.clear(); script(({'content': 'ok'}, {}))
        bob_doc = add(BOB, 'passed', vendor='Bob Co', total=1)
        assistant.answer(ALICE, [], 'what is this?', f'/app/documents/{bob_doc}', bob_doc)
        assert f'#{bob_doc}' not in sent[0][0][0]['content']

        # a tool error goes back to the model, which answers anyway
        sent.clear(); script((call('get_document', {'id': 999999}), {}), ({'content': 'Not found.'}, {}))
        out = assistant.answer(ALICE, [], 'show 999999')
        assert out['reply'] == 'Not found.' and 'error' in sent[1][0][-1]['content'] and out['steps'] == ['Read document #999999']

        # a model that keeps calling tools gets 4 rounds, then must answer
        sent.clear(); script(*[(call('due_bills', {'days': 7}, n), {}) for n in range(10)])
        out = assistant.answer(ALICE, [], 'loop forever')
        assert [c for _, c in sent] == ['auto'] * 4 + ['none'], [c for _, c in sent]

        # only the last 20 history messages are sent
        sent.clear(); script(({'content': 'ok'}, {}))
        assistant.answer(ALICE, [{'role': 'user', 'content': str(n)} for n in range(30)], 'q')
        assert len(sent[0][0]) == 1 + 20 + 1
    finally:
        providers.chat = real


def endpoints():
    from fastapi.testclient import TestClient
    c = TestClient(app.app)
    alice, bob = as_user(ALICE), as_user(BOB)
    real = assistant.answer
    assistant.answer = lambda uid, history, text, page=None, document_id=None: {
        'reply': f'answer to {text} after {len(history)}', 'steps': ['Searched documents'], 'tokens': 10}
    try:
        r = c.post('/assistant/messages', json={'text': 'Top vendors this year? ' * 5}, headers=alice).json()
        chat = r['chat_id']
        assert r['reply'].endswith('after 0') and r['steps'] == ['Searched documents']
        r2 = c.post('/assistant/messages', json={'chat_id': chat, 'text': 'and last month?'}, headers=alice).json()
        assert r2['chat_id'] == chat and r2['reply'].endswith('after 2')  # the first question and answer went along
        listed = c.get('/assistant/chats', headers=alice).json()
        assert [x['id'] for x in listed] == [chat] and len(listed[0]['title']) == 60
        msgs = c.get(f'/assistant/chats/{chat}', headers=alice).json()['messages']
        assert [m['role'] for m in msgs] == ['user', 'assistant'] * 2 and msgs[1]['steps'] == ['Searched documents']

        # Bob can't see, use, or delete Alice's chat
        assert c.get(f'/assistant/chats/{chat}', headers=bob).status_code == 404
        assert c.post('/assistant/messages', json={'chat_id': chat, 'text': 'x'}, headers=bob).status_code == 404
        assert c.delete(f'/assistant/chats/{chat}', headers=bob).status_code == 404
        assert c.delete('/assistant/chats', headers=bob).status_code == 204
        assert c.get('/assistant/chats', headers=bob).json() == []
        assert len(c.get('/assistant/chats', headers=alice).json()) == 1

        assert c.post('/assistant/messages', json={'text': ''}, headers=alice).status_code == 422
        assert c.post('/assistant/messages', json={'text': 'x' * 1001}, headers=alice).status_code == 422

        # a failed answer is not counted
        def busy(*a, **k):
            raise RuntimeError('HTTP 503')
        assistant.answer = busy
        r = c.post('/assistant/messages', json={'text': 'x'}, headers=bob)
        assert r.status_code == 503 and r.json()['detail'] == 'The assistant is busy. Try again in a minute.'
        assistant.answer = lambda *a, **k: {'reply': 'ok', 'steps': [], 'tokens': 1}

        # caps: Alice has 2 answered messages
        app.ASSISTANT_PER_USER = 2
        r = c.post('/assistant/messages', json={'text': 'x'}, headers=alice)
        assert r.status_code == 429 and r.json()['detail'] == "You've used today's 2 messages."
        assert c.post('/assistant/messages', json={'text': 'x'}, headers=bob).status_code == 200  # Bob's 1st
        app.ASSISTANT_PER_USER, app.ASSISTANT_DAILY_LIMIT = 30, 3
        r = c.post('/assistant/messages', json={'text': 'x'}, headers=bob)
        assert r.status_code == 429 and r.json()['detail'] == 'The assistant has reached today\'s limit. Try again tomorrow.'
        app.ASSISTANT_DAILY_LIMIT = 60

        # delete one, delete all
        other = c.post('/assistant/messages', json={'text': 'second chat'}, headers=bob).json()['chat_id']
        assert c.delete(f'/assistant/chats/{other}', headers=bob).status_code == 204
        assert c.get(f'/assistant/chats/{other}', headers=bob).status_code == 404
        assert c.delete('/assistant/chats', headers=alice).status_code == 204
        assert c.get('/assistant/chats', headers=alice).json() == []

        # deleting the account removes chats; answered messages still count app-wide
        c.post('/assistant/messages', json={'text': 'keep?'}, headers=alice)
        assert c.delete('/account', headers=alice).status_code == 204
        with store.conn() as con:
            assert con.execute('SELECT count(*) AS n FROM assistant_chats WHERE user_id = %s', (ALICE,)).fetchone()['n'] == 0
            assert con.execute('SELECT count(*) AS n FROM assistant_messages WHERE user_id = %s', (ALICE,)).fetchone()['n'] == 0
            assert con.execute('SELECT count(*) AS n FROM assistant_messages WHERE user_id IS NULL').fetchone()['n'] == 3
    finally:
        assistant.answer = real


try:
    chat_fallback()
    seeded = tools()
    loop(seeded)
    endpoints()
    print('ok')
finally:
    with store.conn() as con:
        con.execute(f'DROP SCHEMA {store.schema_name()} CASCADE')
