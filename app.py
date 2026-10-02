"""Crosscheck API: upload, AI reading, checks, review, export, webhook to n8n. Run: uvicorn app:app --reload"""
import contextlib
import csv
import hashlib
import hmac
import io
import json
import os
import queue
import threading
import time
import urllib.parse
import urllib.request
from datetime import date, datetime
from typing import Literal

import jwt
import pillow_heif
import pypdfium2
from PIL import Image, ImageOps
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from psycopg.types.json import Jsonb
from pydantic import BaseModel

import providers
import store
from schema import Document
from validate import apply_date_order, suggest, validate

providers.load_env()
pillow_heif.register_heif_opener()   # lets Pillow open iPhone HEIC photos
MODEL = os.environ.get('EXTRACT_MODEL', 'gemini-3.1-flash-lite')
MAX_BYTES = 10 * 1024 * 1024
MAX_FILES = 20
MAX_PDF_PAGES = 20   # also caps model cost: the whole PDF goes to the model
PDF_LOCK = threading.Lock()   # PDFium is not thread-safe; endpoints run in a thread pool
DateOrderValue = Literal['MDY', 'DMY']
DAILY_UPLOAD_LIMIT = int(os.environ.get('DAILY_UPLOAD_LIMIT', 10))   # model reads (uploads + retries) per day: protects the quota


def reads_today(con, uid):
    return con.execute("SELECT count(*) AS n FROM reads WHERE user_id = %s AND at > now() - interval '1 day'", (uid,)).fetchone()['n']

@contextlib.asynccontextmanager
async def lifespan(_):
    threading.Thread(target=resume_stuck, daemon=True).start()
    yield


app = FastAPI(title='Crosscheck API', lifespan=lifespan)
# the web app calls the API from the browser; only its own origin(s) may (comma-separated FRONTEND_ORIGIN)
app.add_middleware(CORSMiddleware, allow_origins=[o.strip().rstrip('/') for o in os.environ.get('FRONTEND_ORIGIN', 'http://localhost:3000').split(',')],
                   allow_methods=['*'], allow_headers=['Authorization', 'Content-Type'], expose_headers=['X-Skipped', 'Content-Disposition'])  # export file names
_jwks = None


def signing_key(token):
    """Supabase's public key for this token, from the project's JWKS endpoint (cached)."""
    global _jwks
    if _jwks is None:
        _jwks = jwt.PyJWKClient(f'{os.environ["SUPABASE_URL"].rstrip("/")}/auth/v1/.well-known/jwks.json')
    return _jwks.get_signing_key_from_jwt(token).key


def current_user(authorization: str | None = Header(None)) -> str:
    """The signed-in user's id, from a Supabase Auth access token. 401 unless the token is valid and unexpired."""
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(401, 'Please sign in.')
    token = authorization.removeprefix('Bearer ')
    try:
        claims = jwt.decode(token, signing_key(token), algorithms=['ES256', 'RS256'], audience='authenticated', options={'require': ['exp', 'sub']}, leeway=30,  # the PC's clock may run a little behind Supabase's
                            issuer=f'{os.environ["SUPABASE_URL"].rstrip("/")}/auth/v1')
    except jwt.PyJWTError:
        raise HTTPException(401, 'Please sign in again.')
    return claims['sub']


COLUMNS = 'id, user_id, file_name, mime, status, document, checks, error, vendor, currency, issue_date, total, model, ' \
          'prompt_version, tokens_in, tokens_out, created_at, updated_at'


def row_by_id(con, doc_id, with_file=False):
    """Internal read without an owner check (background jobs). Endpoints use get_row."""
    return con.execute(f'SELECT {COLUMNS}{", file" if with_file else ""} FROM documents WHERE id = %s', (doc_id,)).fetchone()


def get_row(con, doc_id, uid, with_file=False):
    """The document if it belongs to user uid; 404 otherwise, so other users' ids reveal nothing."""
    r = row_by_id(con, doc_id, with_file)
    if r is None or str(r['user_id']) != uid:
        raise HTTPException(404, 'Document not found.')
    return r


def run_checks(con, uid, doc: Document, order, doc_id=None):
    """validate() plus the one check that needs the user's other documents: an earlier copy of the same invoice."""
    checks = validate(doc, date_order=order)
    dup = store.duplicate_of(con, uid, doc, before_id=doc_id)
    if dup:
        checks.append({'check': 'duplicate', 'fields': ['doc_number'], 'duplicate_of': dup['id'],
                       'message': f'Same vendor, number and total as {dup["doc_number"]}. It was uploaded earlier.'})
    return checks


def save(con, doc_id, doc: Document, status, uid, extra=None, date_order=None, only_if_processing=False):
    """Store a document with its checks. The date order (the user's choice for this document, else the one
    confirmed for the vendor) is applied first. only_if_processing: the background reader writes only while the
    document is still 'processing', so it never replaces corrections saved in the meantime."""
    order = date_order or store.date_order(con, uid, doc.vendor)
    doc = apply_date_order(doc, order)
    checks = run_checks(con, uid, doc, order, doc_id)
    if status is None:
        status = 'needs_review' if checks else 'passed'
    fields = {'document': Jsonb(doc.model_dump(mode='json')), 'checks': Jsonb(checks), 'status': status,
              'error': None, 'vendor': doc.vendor, 'currency': doc.currency, 'issue_date': doc.issue_date,
              'total': doc.total, **(extra or {})}
    if only_if_processing:  # the AI's reading: also kept apart, as the user first sees it, to measure corrections (corrections.py)
        fields['extracted'] = fields['document']
    only = " AND status = 'processing'" if only_if_processing else ''
    con.execute(f'UPDATE documents SET {", ".join(k + " = %s" for k in fields)}, updated_at = now() WHERE id = %s{only}',
                (*fields.values(), doc_id))


def webhook_user():
    return os.environ.get('WEBHOOK_USER_ID', '').strip().lower()


EVENT_LOCK = threading.Lock()  # reading a document and queueing its event happen together, so a stale status never queues last


def send_event(doc_id):
    """POST the document to WEBHOOK_URL (e.g. an n8n workflow that adds a Google Sheets row). Never raises."""
    if not os.environ.get('WEBHOOK_URL'):
        return
    with EVENT_LOCK:
        with store.conn() as con:
            r = row_by_id(con, doc_id)
        if r is None or str(r['user_id']) != webhook_user():
            return  # deleted meanwhile, or another user's document: the one webhook belongs to one account
        post_event({'event': f'document.{r["status"]}', 'id': r['id'], 'file_name': r['file_name'],
                    'status': r['status'], 'document': r['document'], 'checks': r['checks'], 'error': r['error']})


def send_deleted(doc_id, uid):
    """Tell the webhook a document is gone, so its spreadsheet row can be marked deleted."""
    if os.environ.get('WEBHOOK_URL') and uid == webhook_user():
        with EVENT_LOCK:
            post_event({'event': 'document.deleted', 'id': doc_id, 'status': 'deleted'})


EVENTS = queue.Queue()  # one worker delivers in order, so a retried 'passed' never lands after 'reviewed' or 'deleted'


def deliver_events():
    while True:
        url, body, headers, doc_id = EVENTS.get()
        for attempt in range(3):
            try:
                # long timeout: a sleeping free-tier n8n (Render) took 113 s to wake (measured 2026-10-02), then runs the workflow
                with urllib.request.urlopen(urllib.request.Request(url, body, headers), timeout=300):
                    break
            except Exception as e:
                print(f'webhook for document {doc_id} failed (attempt {attempt + 1}): {e}')
                if attempt < 2:
                    time.sleep(2 ** attempt)
        EVENTS.task_done()


# ponytail: in-memory queue; events still waiting are lost on restart, a table if they must survive
threading.Thread(target=deliver_events, daemon=True).start()


def post_event(payload):
    """Queue one event, signed with HMAC-SHA256 of the body in X-Signature.
    The app does not wait; tests call EVENTS.join()."""
    secret = os.environ.get('WEBHOOK_SECRET')
    if not secret:
        print(f'webhook for document {payload["id"]} not sent: WEBHOOK_SECRET is not set')  # n8n would reject it anyway
        return
    body = json.dumps(payload).encode()
    headers = {'Content-Type': 'application/json', 'User-Agent': 'receipt-extractor/0.1',
               'X-Signature': 'sha256=' + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()}
    EVENTS.put((os.environ['WEBHOOK_URL'], body, headers, payload['id']))


def public_error(e):
    """Short message for the review screen; the full error goes to the server log only."""
    print(f'extraction failed: {e!r}')
    text = str(e)
    if 'daily quota used up' in text:
        return "Today's AI limit is used up. Try again tomorrow."
    if 'HTTP 503' in text or 'HTTP 429' in text:
        return 'The AI service is busy. Try again in a few minutes.'
    if 'no answer from the model service' in text:
        return 'The AI service did not answer. Try again.'
    if isinstance(e, ValueError):
        return 'The AI reply could not be read. Try again.'
    return 'Reading failed. Try again.'


def process(doc_id):
    """Background job: send the file to the model, parse, check, store. Failures are stored, never raised."""
    try:
        with store.conn() as con:
            row = row_by_id(con, doc_id, with_file=True)
        if row is None:
            return  # deleted before extraction started
        text, tin, tout, _ = providers.call(MODEL, bytes(row['file']))
        doc = providers.parse(text)
        extra = {'model': MODEL, 'prompt_version': hashlib.sha256(providers.PROMPT.encode()).hexdigest()[:8],
                 'tokens_in': tin, 'tokens_out': tout}
        with store.conn() as con:
            save(con, doc_id, doc, None, str(row['user_id']), extra, only_if_processing=True)
            done = row_by_id(con, doc_id)
        read = done is not None   # None: deleted meanwhile
    except Exception as e:
        with store.conn() as con:
            failed = con.execute("UPDATE documents SET status = 'failed', error = %s, updated_at = now() "
                                 "WHERE id = %s AND status = 'processing'", (public_error(e), doc_id)).rowcount
        if failed:
            send_event(doc_id)  # document.failed: an alert, the file could not be read
        return
    if read:
        send_event(doc_id)  # passed or needs_review; outside the try: a webhook problem never marks a good document failed


def resume_stuck():
    """At startup: documents still 'processing' lost their background job when the server stopped; read them again.
    ponytail: assumes one API process; with several, claim rows first (UPDATE ... RETURNING) so none is read twice."""
    try:
        with store.conn() as con:
            ids = [r['id'] for r in con.execute("SELECT id FROM documents WHERE status = 'processing' ORDER BY id")]
    except Exception as e:
        print(f'resuming stuck documents failed: {e!r}')
        return []
    for doc_id in ids:
        process(doc_id)   # never raises; failures are stored on the document
    return ids


@app.middleware('http')
async def limit_upload_size(request, call_next):
    """Refuse oversized requests before the body is read.
    ponytail: relies on Content-Length; chunked uploads skip this check (Render has no body limit setting) and spool to disk."""
    if int(request.headers.get('content-length') or 0) > MAX_FILES * MAX_BYTES + 1024 * 1024:
        return Response('request too large', status_code=413)
    return await call_next(request)


HEIF_BRANDS = (b'heic', b'heix', b'hevc', b'hevx', b'heim', b'heis', b'mif1', b'msf1')


def heic_to_jpeg(data):
    """iPhone photos (HEIC/HEIF) become JPEG on upload, so the model, the review screen and every browser can show
    them. Anything else, or a HEIC that can't be decoded, is returned unchanged (and then rejected as unsupported)."""
    if data[4:8] != b'ftyp' or data[8:12] not in HEIF_BRANDS:
        return data
    try:
        img = Image.open(io.BytesIO(data))
        # ponytail: 48 MP "HEIF Max" photos are refused (~150 MB per decoded copy, the free server has 512 MB);
        # the usual 12/24 MP photos pass. Shrink while decoding if 48 MP receipts turn up.
        if img.width * img.height > 40_000_000:
            print(f'HEIC too large to convert: {img.width}x{img.height}')
            return data
        img = ImageOps.exif_transpose(img).convert('RGB')  # keep the phone's rotation
        buf = io.BytesIO()
        img.save(buf, 'JPEG', quality=90)
        return buf.getvalue()
    except Exception as e:
        print(f'HEIC conversion failed: {e!r}')
        return data


@app.post('/documents', status_code=202)
def upload(files: list[UploadFile], tasks: BackgroundTasks, uid: str = Depends(current_user)):
    """Upload up to 20 files (PDF, JPG, PNG, WebP, HEIC; max 10 MB each). Extraction runs in the background.
    A plain def: FastAPI runs it in a thread, so the database writes don't block other requests."""
    if not files or len(files) > MAX_FILES:
        raise HTTPException(400, f'Send 1 to {MAX_FILES} files.')
    with store.conn() as con:
        used = reads_today(con, uid)
    # ponytail: counted once per request; two parallel uploads can overshoot the limit slightly
    left = DAILY_UPLOAD_LIMIT - used
    if left <= 0:
        raise HTTPException(429, f"You have used today's {DAILY_UPLOAD_LIMIT} reads. Try again tomorrow.")
    created = []
    for f in files:
        if left <= 0:
            created.append({'file_name': f.filename, 'error': 'Daily limit reached. Try again tomorrow.'})
            continue
        data = heic_to_jpeg(f.file.read(MAX_BYTES + 1))
        kind = providers.mime(data)  # type from the file's bytes, never from its name
        if kind is None:
            created.append({'file_name': f.filename, 'error': 'Not a PDF, JPG, PNG, WebP or HEIC file.'})
            continue
        if len(data) > MAX_BYTES:  # also a HEIC photo that grew past the limit when converted to JPEG
            created.append({'file_name': f.filename, 'error': 'Larger than 10 MB.'})
            continue
        if kind == 'application/pdf':
            pages = pdf_pages(data)
            if not 1 <= pages <= MAX_PDF_PAGES:
                created.append({'file_name': f.filename, 'error': f'PDF must be readable with 1 to {MAX_PDF_PAGES} pages'})
                continue
        with store.conn() as con:
            doc_id = con.execute("INSERT INTO documents (user_id, file_name, mime, file, status) "
                                 "VALUES (%s, %s, %s, %s, 'processing') RETURNING id",
                                 (uid, os.path.basename(f.filename or 'upload'), kind, data)).fetchone()['id']
            con.execute('INSERT INTO reads (user_id) VALUES (%s)', (uid,))
        left -= 1
        tasks.add_task(process, doc_id)
        created.append({'id': doc_id, 'file_name': f.filename, 'status': 'processing'})
    return created


@app.get('/documents')
def list_documents(status: str | None = None, q: str | None = None, date_from: date | None = None,
                   date_to: date | None = None, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                   oldest: bool = False, uid: str = Depends(current_user)):
    """History: newest first (oldest first for the review queue). q searches vendor and file name; dates filter on
    the document's issue date."""
    sql = 'SELECT id, file_name, status, vendor, currency, issue_date, total, created_at FROM documents WHERE user_id = %s'
    args = [uid]
    if status:
        sql += ' AND status = %s'; args.append(status)
    if q:
        like = '%' + q.replace('\\', '\\\\').replace('%', r'\%').replace('_', r'\_') + '%'  # % and _ typed are literal
        sql += ' AND (vendor ILIKE %s OR file_name ILIKE %s)'; args += [like] * 2
    if date_from:
        sql += ' AND issue_date >= %s'; args.append(date_from)
    if date_to:
        sql += ' AND issue_date <= %s'; args.append(date_to)
    sql += f' ORDER BY id {"ASC" if oldest else "DESC"} LIMIT %s OFFSET %s'
    with store.conn() as con:
        return con.execute(sql, (*args, limit, offset)).fetchall()


@app.get('/documents/{doc_id}')
def get_document(doc_id: int, uid: str = Depends(current_user)):
    """The document; a flagged one also gets a suggested fix for the review screen (None when there is none)."""
    with store.conn() as con:
        r = get_row(con, doc_id, uid)
    r['suggestion'] = suggest(Document(**r['document'])) if r['status'] == 'needs_review' and r['document'] else None
    return r


@app.post('/check')
def check(doc: Document, date_order: DateOrderValue | None = None, doc_id: int | None = None,
          uid: str = Depends(current_user)):
    """Run the checks without saving, so the review screen can show them while the user edits.
    doc_id: the document being edited, so it is compared only with documents uploaded before it.
    Returns the document with printed dates re-read in the date order, the failed checks and a suggested fix."""
    with store.conn() as con:
        order = date_order or store.date_order(con, uid, doc.vendor)
        doc = apply_date_order(doc, order)
        return {'document': doc, 'checks': run_checks(con, uid, doc, order, doc_id), 'suggestion': suggest(doc)}


@app.put('/documents/{doc_id}')
def update_document(doc_id: int, doc: Document, tasks: BackgroundTasks, date_order: DateOrderValue | None = None,
                    if_unchanged_since: datetime | None = None, uid: str = Depends(current_user)):
    """Save the user's corrections. Checks run again; the document is marked reviewed and sent to the webhook.
    date_order: the user's reading of this document's printed dates (MDY/DMY), when only this one is confirmed.
    if_unchanged_since: the updated_at the editor loaded; a later change (another tab) is not overwritten."""
    with store.conn() as con:
        row = get_row(con, doc_id, uid)
        if row['status'] == 'processing':
            raise HTTPException(409, 'Still being read. Save again when it is done.')
        if if_unchanged_since and row['updated_at'] != if_unchanged_since:
            raise HTTPException(409, 'Changed in another tab. Reload to see the latest version.')
        save(con, doc_id, doc, 'reviewed', uid, date_order=date_order)
    tasks.add_task(send_event, doc_id)
    return get_document(doc_id, uid)


@app.post('/documents/{doc_id}/retry', status_code=202)
def retry(doc_id: int, tasks: BackgroundTasks, uid: str = Depends(current_user)):
    """Run extraction again. Only for failed or needs_review documents: a reviewed document keeps the
    user's corrections, and one still processing is not sent to the model twice."""
    with store.conn() as con:  # one statement, so two quick clicks can't both start a read
        if reads_today(con, uid) >= DAILY_UPLOAD_LIMIT:
            raise HTTPException(429, f"You have used today's {DAILY_UPLOAD_LIMIT} reads. Try again tomorrow.")
        claimed = con.execute("UPDATE documents SET status = 'processing', error = NULL, updated_at = now() "
                              "WHERE id = %s AND user_id = %s AND status IN ('failed', 'needs_review') RETURNING id",
                              (doc_id, uid)).fetchone()
        if claimed is None:
            get_row(con, doc_id, uid)  # 404 for ids that are not the user's
            raise HTTPException(409, 'Only failed or flagged documents can be read again.')
        con.execute('INSERT INTO reads (user_id) VALUES (%s)', (uid,))
    tasks.add_task(process, doc_id)
    return {'id': doc_id, 'status': 'processing'}


@app.delete('/documents/{doc_id}', status_code=204)
def delete_document(doc_id: int, tasks: BackgroundTasks, uid: str = Depends(current_user)):
    """Delete the record together with the uploaded file."""
    with store.conn() as con:
        gone = con.execute('DELETE FROM documents WHERE id = %s AND user_id = %s RETURNING status', (doc_id, uid)).fetchone()
    if gone is None:
        raise HTTPException(404, 'Document not found.')
    if gone['status'] in ('passed', 'reviewed'):  # only checked documents have a spreadsheet row to mark
        tasks.add_task(send_deleted, doc_id, uid)


@app.get('/documents/{doc_id}/file')
def get_file(doc_id: int, uid: str = Depends(current_user)):
    with store.conn() as con:
        r = get_row(con, doc_id, uid, with_file=True)
    # RFC 5987 form: any language in the name, and no quotes or line breaks can reach the header
    return Response(bytes(r['file']), media_type=r['mime'],
                    headers={'Content-Disposition': f"inline; filename*=UTF-8''{urllib.parse.quote(r['file_name'])}"})


def pdf_pages(data):
    """Page count of a PDF, 0 if it can't be read."""
    with PDF_LOCK:
        try:
            pdf = pypdfium2.PdfDocument(bytes(data))
        except pypdfium2.PdfiumError:
            return 0
        try:
            return len(pdf)
        finally:
            pdf.close()


@app.get('/documents/{doc_id}/pages')
def page_count(doc_id: int, uid: str = Depends(current_user)):
    with store.conn() as con:
        r = get_row(con, doc_id, uid, with_file=True)
    return {'pages': pdf_pages(r['file']) if r['mime'] == 'application/pdf' else 1}


@app.get('/documents/{doc_id}/pages/{n}')
def page_image(doc_id: int, n: int, uid: str = Depends(current_user)):
    """Page n (from 0) as an image for the review screen. PDFs are rendered; images are returned as is."""
    with store.conn() as con:
        r = get_row(con, doc_id, uid, with_file=True)
    if r['mime'] != 'application/pdf':
        if n != 0:
            raise HTTPException(404, 'Page not found.')
        return Response(bytes(r['file']), media_type=r['mime'])
    buf = io.BytesIO()
    with PDF_LOCK:
        pdf = pypdfium2.PdfDocument(bytes(r['file']))
        try:
            if not 0 <= n < len(pdf):
                raise HTTPException(404, 'Page not found.')
            page = pdf[n]
            scale = min(2, 2000 / max(page.get_size()))  # at most 2000 px on the long side, whatever the page size
            page.render(scale=scale).to_pil().save(buf, 'PNG')
        finally:
            pdf.close()
    return Response(buf.getvalue(), media_type='image/png')


class DateOrder(BaseModel):
    date_order: str


@app.put('/vendors/{vendor}/date-order')
def set_vendor_date_order(vendor: str, body: DateOrder, tasks: BackgroundTasks, uid: str = Depends(current_user)):
    """Confirm how this vendor prints dates (MDY or DMY). Unreviewed documents of the vendor are re-checked;
    those that now pass are sent to the webhook."""
    if body.date_order not in ('MDY', 'DMY'):
        raise HTTPException(422, 'date_order must be MDY or DMY.')
    with store.conn() as con:
        store.set_date_order(con, uid, vendor, body.date_order)
        rows = [r for r in con.execute("SELECT id, vendor, document FROM documents WHERE user_id = %s "
                                       "AND status = 'needs_review'", (uid,)).fetchall()
                if store.vendor_key(r['vendor']) == store.vendor_key(vendor)]
        for r in rows:
            save(con, r['id'], Document.model_validate(r['document']), None, uid)
            if row_by_id(con, r['id'])['status'] == 'passed':
                tasks.add_task(send_event, r['id'])
    return {'vendor': vendor, 'date_order': body.date_order, 'rechecked': len(rows)}


def delete_auth_user(uid):
    """Remove the sign-in account with Supabase's Admin API (SUPABASE_SECRET_KEY, backend only). Raises on failure."""
    key = os.environ.get('SUPABASE_SECRET_KEY')
    if not key:
        raise HTTPException(503, 'Account deletion is not set up on this server.')
    url = f'{os.environ["SUPABASE_URL"].rstrip("/")}/auth/v1/admin/users/{uid}'
    try:
        urllib.request.urlopen(urllib.request.Request(url, method='DELETE', headers={'apikey': key, 'Authorization': f'Bearer {key}'}),
                               timeout=15)
    except urllib.error.HTTPError as e:
        if e.code != 404:  # 404: already removed by an earlier try whose answer was lost, so a retry still finishes
            raise


@app.delete('/account', status_code=204)
def delete_account(uid: str = Depends(current_user)):
    """Delete the user's documents, files and settings, then the sign-in account. If the account can't be
    removed, nothing is deleted (the database changes roll back)."""
    with store.conn() as con:
        con.execute('DELETE FROM documents WHERE user_id = %s', (uid,))
        con.execute('DELETE FROM vendor_date_orders WHERE user_id = %s', (uid,))
        con.execute('DELETE FROM reads WHERE user_id = %s', (uid,))
        try:
            delete_auth_user(uid)
        except HTTPException:
            raise
        except Exception as e:
            print(f'deleting auth user {uid} failed: {e!r}')
            raise HTTPException(502, 'Could not delete the account. Please try again.')


@app.get('/usage')
def usage(uid: str = Depends(current_user)):
    """Model reads (uploads + retries) used in the last 24 hours and the daily limit, for the upload page."""
    with store.conn() as con:
        return {'used': reads_today(con, uid), 'limit': DAILY_UPLOAD_LIMIT}


@app.get('/stats')
def stats(date_from: date | None = None, uid: str = Depends(current_user)):
    """Dashboard numbers for the user. Money is summed per currency (never converted), and only from checked
    documents (passed or reviewed): amounts still waiting for review are not counted as spend.
    date_from limits the money figures to documents issued on or after it (undated ones drop out); counts stay all-time."""
    with store.conn() as con:
        q = lambda cols, rest='', args=(): con.execute(f'SELECT {cols} FROM documents WHERE user_id = %s {rest}', (uid, *args)).fetchall()
        checked = "AND status IN ('passed', 'reviewed')" + (' AND issue_date >= %s' if date_from else '')
        m = lambda cols, rest: q(cols, f'{checked} {rest}', (date_from,) if date_from else ())
        return {
            'documents': q('count(*) AS n')[0]['n'],
            'by_status': {r['status']: r['n'] for r in q('status, count(*) AS n', 'GROUP BY status')},
            'spend_by_currency': m('currency, sum(total) AS total, count(*) AS n', 'AND total IS NOT NULL GROUP BY currency'),
            'tax_by_currency': m("currency, sum((document->>'tax')::numeric) AS total, count(*) AS n",
                                 "AND document->>'tax' IS NOT NULL GROUP BY currency"),
            'top_vendors': m('min(vendor) AS vendor, currency, sum(total) AS total, count(*) AS n',
                             'AND vendor IS NOT NULL GROUP BY lower(vendor), currency ORDER BY total DESC NULLS LAST LIMIT 10'),
            'by_month': m("to_char(issue_date, 'YYYY-MM') AS month, currency, sum(total) AS total, count(*) AS n",
                          'AND issue_date IS NOT NULL GROUP BY month, currency ORDER BY month'),
        }


DOC_COLUMNS = ['id', 'file_name', 'status', 'doc_type', 'vendor', 'branch', 'buyer', 'doc_number', 'issue_date', 'due_date',
               'currency', 'subtotal', 'discount', 'tax', 'service_charge', 'total']
ITEM_COLUMNS = ['document_id', 'description', 'quantity', 'unit_price', 'amount', 'discount']


def export_rows(uid, status):
    """(document rows, item rows) for export; failed documents are left out."""
    sql = "SELECT id, file_name, status, document FROM documents WHERE user_id = %s AND status != 'failed' AND document IS NOT NULL"
    args = [uid]
    if status:
        sql += ' AND status = %s'; args.append(status)
    docs, items = [], []
    with store.conn() as con:
        for r in con.execute(sql + ' ORDER BY id', args):
            d = r['document']
            docs.append([r['id'], r['file_name'], r['status']] + [d.get(k) for k in DOC_COLUMNS[3:]])
            items += [[r['id']] + [i.get(k) for k in ITEM_COLUMNS[1:]] for i in d.get('items') or []]
    return docs, items


NUMERIC = {'subtotal', 'discount', 'tax', 'service_charge', 'total', 'quantity', 'unit_price', 'amount'}


def cell(column, v):
    """One export cell. Money and quantities become numbers; all other text stays text (invoice number 00123
    keeps its zeros). Text starting with = + - @ tab or CR gets a leading ' so a spreadsheet never runs it as a formula."""
    if v is None:
        return None
    if column in NUMERIC:
        return float(v)
    if isinstance(v, str) and v[:1] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + v
    return v


def cells(columns, row_):
    return [cell(c, v) for c, v in zip(columns, row_)]


# QuickBooks Online "Import bills" layout; headers are matched to QuickBooks fields during the import.
QB_COLUMNS = ['Bill no.', 'Supplier', 'Bill Date', 'Due Date', 'Account', 'Line Description', 'Line Amount', 'Line Tax Code']


def quickbooks_rows(uid):
    """(rows, skipped): one row per bill line, only for checked documents (passed or reviewed).
    Lines are the items plus service charge, tax and discount, so they add up to the total; if they don't
    (e.g. a cash-rounded total), the bill gets one line with the total. Documents without a date or total
    are skipped: QuickBooks needs both. Account is a placeholder the user maps to an expense account."""
    rows, skipped = [], 0
    with store.conn() as con:
        found = con.execute("SELECT id, document FROM documents WHERE user_id = %s AND status IN ('passed', 'reviewed') "
                            'ORDER BY id', (uid,))
        for r in found:
            d = Document.model_validate(r['document'])
            if d.issue_date is None or d.total is None:
                skipped += 1
                continue
            items = [(i.description, i.amount - (i.discount or 0)) for i in d.items if i.amount is not None]
            extra = [(name, v) for name, v in (('Service charge', d.service_charge), ('Discount', -d.discount if d.discount else None)) if v]
            # tax added on top gets its own line; "VAT included" is already inside the items. Whichever adds up wins.
            lines = next((ls for ls in (items + extra + ([('Tax', d.tax)] if d.tax else []), items + extra)
                          if items and sum(v for _, v in ls) == d.total), [('Total', d.total)])
            # ponytail: US date order; QuickBooks asks for the file's date format on import
            bill = [cell('text', d.doc_number or f'CC-{r["id"]}'), cell('text', d.vendor or 'Unknown supplier'),
                    f'{d.issue_date:%m/%d/%Y}', f'{(d.due_date or d.issue_date):%m/%d/%Y}', 'Uncategorized Expense']
            rows += [bill + [cell('text', desc), f'{v:.2f}', None] for desc, v in lines]
    return rows, skipped


@app.get('/export')
def export(format: str = 'xlsx', status: str | None = None, uid: str = Depends(current_user)):
    """Download documents as CSV (one row per document), XLSX (Documents and Items sheets) or a QuickBooks
    Online bill import CSV (X-Skipped header: documents left out for a missing date or total)."""
    if format not in ('csv', 'xlsx', 'quickbooks'):
        raise HTTPException(422, 'Format must be csv, xlsx or quickbooks.')
    if format == 'quickbooks':
        rows, skipped = quickbooks_rows(uid)
        buf = io.StringIO()
        csv.writer(buf).writerows([QB_COLUMNS] + rows)
        return Response(buf.getvalue().encode('utf-8-sig'), media_type='text/csv', headers={
            'Content-Disposition': 'attachment; filename="quickbooks-bills.csv"', 'X-Skipped': str(skipped)})
    docs, items = export_rows(uid, status)
    if format == 'csv':
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(DOC_COLUMNS)
        w.writerows(cells(DOC_COLUMNS, r) for r in docs)
        return Response(buf.getvalue().encode('utf-8-sig'), media_type='text/csv',
                        headers={'Content-Disposition': 'attachment; filename="documents.csv"'})
    from openpyxl import Workbook
    wb = Workbook()
    for ws, cols, rows in ((wb.active, DOC_COLUMNS, docs), (wb.create_sheet('Items'), ITEM_COLUMNS, items)):
        ws.append(cols)
        for row_ in rows:
            ws.append([date.fromisoformat(v) if c in ('issue_date', 'due_date') and v else v for c, v in zip(cols, cells(cols, row_))])
        for row_ in ws.iter_rows(min_row=2):  # real dates, so Excel's date filters and sorting work
            for x in row_:
                if isinstance(x.value, date):
                    x.number_format = 'yyyy-mm-dd'
    wb.active.title = 'Documents'
    buf = io.BytesIO()
    wb.save(buf)
    return Response(buf.getvalue(), media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition': 'attachment; filename="documents.xlsx"'})
