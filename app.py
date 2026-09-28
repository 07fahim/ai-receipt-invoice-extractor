"""Receipt & Invoice Extractor API.

Run:  uvicorn app:app --reload        (docs at http://127.0.0.1:8000/docs)
Needs DATABASE_URL (PostgreSQL, e.g. Supabase session pooler), SUPABASE_URL and GEMINI_API_KEY in .env.
Every request except the docs needs a Supabase Auth access token ('Authorization: Bearer ...'); users only
ever see their own documents. Optional DAILY_UPLOAD_LIMIT (default 50 files per user per 24 hours).
Optional WEBHOOK_URL (+ WEBHOOK_SECRET): each passed or reviewed document is sent there, e.g. to n8n.
Upload -> background extraction (vision LLM) -> checks -> review/correct -> history, stats, export.
"""
import contextlib
import csv
import hashlib
import hmac
import io
import json
import os
import threading
import time
import urllib.parse
import urllib.request
from datetime import date
from typing import Literal

import jwt
import pypdfium2
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from psycopg.types.json import Jsonb
from pydantic import BaseModel

import providers
import store
from schema import Document
from validate import apply_date_order, validate

providers.load_env()
MODEL = os.environ.get('EXTRACT_MODEL', 'gemini-3.1-flash-lite')
MAX_BYTES = 10 * 1024 * 1024
MAX_FILES = 20
MAX_PDF_PAGES = 20   # also caps model cost: the whole PDF goes to the model
PDF_LOCK = threading.Lock()   # PDFium is not thread-safe; endpoints run in a thread pool
DateOrderValue = Literal['MDY', 'DMY']
DAILY_UPLOAD_LIMIT = int(os.environ.get('DAILY_UPLOAD_LIMIT', 50))   # protects the model quota

@contextlib.asynccontextmanager
async def lifespan(_):
    threading.Thread(target=resume_stuck, daemon=True).start()
    yield


app = FastAPI(title='Crosscheck API', lifespan=lifespan)
# the web app calls the API from the browser; only its own origin(s) may (comma-separated FRONTEND_ORIGIN)
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get('FRONTEND_ORIGIN', 'http://localhost:3000').split(','),
                   allow_methods=['*'], allow_headers=['Authorization', 'Content-Type'], expose_headers=['X-Skipped'])
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
        raise HTTPException(401, 'sign in required')
    token = authorization.removeprefix('Bearer ')
    try:
        claims = jwt.decode(token, signing_key(token), algorithms=['ES256', 'RS256'], audience='authenticated',
                            issuer=f'{os.environ["SUPABASE_URL"].rstrip("/")}/auth/v1')
    except jwt.PyJWTError:
        raise HTTPException(401, 'sign in again')
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
        raise HTTPException(404, 'document not found')
    return r


def run_checks(con, uid, doc: Document, order, doc_id=None):
    """validate() plus the one check that needs the user's other documents: an earlier copy of the same invoice."""
    checks = validate(doc, date_order=order)
    dup = store.duplicate_of(con, uid, doc, before_id=doc_id)
    if dup:
        checks.append({'check': 'duplicate', 'fields': ['doc_number'], 'duplicate_of': dup['id'],
                       'message': f'Same vendor, number and total as {dup["doc_number"]}, uploaded earlier'})
    return checks


def save(con, doc_id, doc: Document, status, uid, extra=None, date_order=None):
    """Store a document with its checks. The date order (the user's choice for this document, else the one
    confirmed for the vendor) is applied first."""
    order = date_order or store.date_order(con, uid, doc.vendor)
    doc = apply_date_order(doc, order)
    checks = run_checks(con, uid, doc, order, doc_id)
    if status is None:
        status = 'needs_review' if checks else 'passed'
    fields = {'document': Jsonb(doc.model_dump(mode='json')), 'checks': Jsonb(checks), 'status': status,
              'error': None, 'vendor': doc.vendor, 'currency': doc.currency, 'issue_date': doc.issue_date,
              'total': doc.total, **(extra or {})}
    con.execute(f'UPDATE documents SET {", ".join(k + " = %s" for k in fields)}, updated_at = now() WHERE id = %s',
                (*fields.values(), doc_id))


def send_event(doc_id):
    """POST the document to WEBHOOK_URL (e.g. an n8n workflow that adds a Google Sheets row).
    Signed with HMAC-SHA256 of the body in X-Signature when WEBHOOK_SECRET is set. Never raises."""
    url = os.environ.get('WEBHOOK_URL')
    if not url:
        return
    with store.conn() as con:
        r = row_by_id(con, doc_id)
    body = json.dumps({'event': f'document.{r["status"]}', 'id': r['id'], 'file_name': r['file_name'],
                       'status': r['status'], 'document': r['document'], 'checks': r['checks']}).encode()
    headers = {'Content-Type': 'application/json', 'User-Agent': 'receipt-extractor/0.1'}
    secret = os.environ.get('WEBHOOK_SECRET')
    if secret:
        headers['X-Signature'] = 'sha256=' + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    # ponytail: in-process retries on a side thread; a queue if deliveries must survive restarts
    def deliver():
        for attempt in range(3):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, body, headers), timeout=10):
                    return
            except Exception as e:
                print(f'webhook for document {doc_id} failed (attempt {attempt + 1}): {e}')
                if attempt < 2:
                    time.sleep(2 ** attempt)
    worker = threading.Thread(target=deliver, daemon=True)
    worker.start()
    return worker  # tests join it; the app does not wait


def public_error(e):
    """Short message for the review screen; the full error goes to the server log only."""
    print(f'extraction failed: {e!r}')
    text = str(e)
    if 'HTTP 503' in text or 'HTTP 429' in text:
        return 'The AI service is busy. Please retry in a few minutes.'
    if 'no answer from the model service' in text:
        return 'The AI service did not answer. Please retry.'
    if isinstance(e, ValueError):
        return 'The AI answer could not be read as a document. Please retry.'
    return 'Extraction failed. Please retry.'


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
            save(con, doc_id, doc, None, str(row['user_id']), extra)
            done = row_by_id(con, doc_id)
        passed = done is not None and done['status'] == 'passed'   # None: deleted meanwhile
    except Exception as e:
        with store.conn() as con:
            con.execute("UPDATE documents SET status = 'failed', error = %s, updated_at = now() WHERE id = %s",
                        (public_error(e), doc_id))
        return
    if passed:
        send_event(doc_id)  # outside the try: a webhook problem never marks a good document failed


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
    ponytail: relies on Content-Length; the host/proxy body limit covers chunked uploads (set it at deploy)."""
    if int(request.headers.get('content-length') or 0) > MAX_FILES * MAX_BYTES + 1024 * 1024:
        return Response('request too large', status_code=413)
    return await call_next(request)


@app.post('/documents', status_code=202)
def upload(files: list[UploadFile], tasks: BackgroundTasks, uid: str = Depends(current_user)):
    """Upload up to 20 files (PDF, JPG, PNG, WebP; max 10 MB each). Extraction runs in the background.
    A plain def: FastAPI runs it in a thread, so the database writes don't block other requests."""
    if not files or len(files) > MAX_FILES:
        raise HTTPException(400, f'send 1 to {MAX_FILES} files')
    with store.conn() as con:
        used = con.execute("SELECT count(*) AS n FROM documents WHERE user_id = %s AND created_at > now() - interval '1 day'",
                           (uid,)).fetchone()['n']
    # ponytail: counted once per request; two parallel uploads can overshoot the limit slightly
    left = DAILY_UPLOAD_LIMIT - used
    if left <= 0:
        raise HTTPException(429, f'daily limit of {DAILY_UPLOAD_LIMIT} files reached; try again tomorrow')
    created = []
    for f in files:
        if left <= 0:
            created.append({'file_name': f.filename, 'error': f'daily limit of {DAILY_UPLOAD_LIMIT} files reached'})
            continue
        data = f.file.read(MAX_BYTES + 1)
        kind = providers.mime(data)  # type from the file's bytes, never from its name
        if len(data) > MAX_BYTES or kind is None:
            created.append({'file_name': f.filename, 'error': 'not a PDF/JPG/PNG/WebP file under 10 MB'})
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
        left -= 1
        tasks.add_task(process, doc_id)
        created.append({'id': doc_id, 'file_name': f.filename, 'status': 'processing'})
    return created


@app.get('/documents')
def list_documents(status: str | None = None, q: str | None = None, date_from: date | None = None,
                   date_to: date | None = None, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                   uid: str = Depends(current_user)):
    """History: newest first. q searches vendor and file name; dates filter on the document's issue date."""
    sql = 'SELECT id, file_name, status, vendor, currency, issue_date, total, created_at FROM documents WHERE user_id = %s'
    args = [uid]
    if status:
        sql += ' AND status = %s'; args.append(status)
    if q:
        sql += ' AND (vendor ILIKE %s OR file_name ILIKE %s)'; args += [f'%{q}%'] * 2
    if date_from:
        sql += ' AND issue_date >= %s'; args.append(date_from)
    if date_to:
        sql += ' AND issue_date <= %s'; args.append(date_to)
    sql += ' ORDER BY id DESC LIMIT %s OFFSET %s'
    with store.conn() as con:
        return con.execute(sql, (*args, limit, offset)).fetchall()


@app.get('/documents/{doc_id}')
def get_document(doc_id: int, uid: str = Depends(current_user)):
    with store.conn() as con:
        return get_row(con, doc_id, uid)


@app.post('/check')
def check(doc: Document, date_order: DateOrderValue | None = None, doc_id: int | None = None,
          uid: str = Depends(current_user)):
    """Run the checks without saving, so the review screen can show them while the user edits.
    doc_id: the document being edited, so it is compared only with documents uploaded before it.
    Returns the document with printed dates re-read in the date order, and the failed checks."""
    with store.conn() as con:
        order = date_order or store.date_order(con, uid, doc.vendor)
        doc = apply_date_order(doc, order)
        return {'document': doc, 'checks': run_checks(con, uid, doc, order, doc_id)}


@app.put('/documents/{doc_id}')
def update_document(doc_id: int, doc: Document, tasks: BackgroundTasks, date_order: DateOrderValue | None = None,
                    uid: str = Depends(current_user)):
    """Save the user's corrections. Checks run again; the document is marked reviewed and sent to the webhook.
    date_order: the user's reading of this document's printed dates (MDY/DMY), when only this one is confirmed."""
    with store.conn() as con:
        get_row(con, doc_id, uid)
        save(con, doc_id, doc, 'reviewed', uid, date_order=date_order)
    tasks.add_task(send_event, doc_id)
    return get_document(doc_id, uid)


@app.post('/documents/{doc_id}/retry', status_code=202)
def retry(doc_id: int, tasks: BackgroundTasks, uid: str = Depends(current_user)):
    """Run extraction again. Only for failed or needs_review documents: a reviewed document keeps the
    user's corrections, and one still processing is not sent to the model twice."""
    with store.conn() as con:
        if get_row(con, doc_id, uid)['status'] not in ('failed', 'needs_review'):
            raise HTTPException(409, 'only failed or needs_review documents can be retried')
        con.execute("UPDATE documents SET status = 'processing', error = NULL, updated_at = now() WHERE id = %s", (doc_id,))
    tasks.add_task(process, doc_id)
    return {'id': doc_id, 'status': 'processing'}


@app.delete('/documents/{doc_id}', status_code=204)
def delete_document(doc_id: int, uid: str = Depends(current_user)):
    """Delete the record together with the uploaded file."""
    with store.conn() as con:
        if con.execute('DELETE FROM documents WHERE id = %s AND user_id = %s', (doc_id, uid)).rowcount == 0:
            raise HTTPException(404, 'document not found')


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
            raise HTTPException(404, 'page not found')
        return Response(bytes(r['file']), media_type=r['mime'])
    buf = io.BytesIO()
    with PDF_LOCK:
        pdf = pypdfium2.PdfDocument(bytes(r['file']))
        try:
            if not 0 <= n < len(pdf):
                raise HTTPException(404, 'page not found')
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
        raise HTTPException(422, 'date_order must be MDY or DMY')
    with store.conn() as con:
        store.set_date_order(con, uid, vendor, body.date_order)
        rows = con.execute("SELECT id, document FROM documents WHERE user_id = %s AND lower(vendor) = %s "
                           "AND status = 'needs_review'", (uid, vendor.strip().lower())).fetchall()
        for r in rows:
            save(con, r['id'], Document.model_validate(r['document']), None, uid)
            if row_by_id(con, r['id'])['status'] == 'passed':
                tasks.add_task(send_event, r['id'])
    return {'vendor': vendor, 'date_order': body.date_order, 'rechecked': len(rows)}


def delete_auth_user(uid):
    """Remove the sign-in account with Supabase's Admin API (SUPABASE_SECRET_KEY, backend only). Raises on failure."""
    key = os.environ.get('SUPABASE_SECRET_KEY')
    if not key:
        raise HTTPException(503, 'account deletion is not set up on this server')
    url = f'{os.environ["SUPABASE_URL"].rstrip("/")}/auth/v1/admin/users/{uid}'
    urllib.request.urlopen(urllib.request.Request(url, method='DELETE', headers={'apikey': key, 'Authorization': f'Bearer {key}'}),
                           timeout=15)


@app.delete('/account', status_code=204)
def delete_account(uid: str = Depends(current_user)):
    """Delete the user's documents, files and settings, then the sign-in account. If the account can't be
    removed, nothing is deleted (the database changes roll back)."""
    with store.conn() as con:
        con.execute('DELETE FROM documents WHERE user_id = %s', (uid,))
        con.execute('DELETE FROM vendor_date_orders WHERE user_id = %s', (uid,))
        try:
            delete_auth_user(uid)
        except HTTPException:
            raise
        except Exception as e:
            print(f'deleting auth user {uid} failed: {e!r}')
            raise HTTPException(502, 'Could not delete the account. Please try again.')


@app.get('/stats')
def stats(uid: str = Depends(current_user)):
    """Dashboard numbers for the user. Money is summed per currency (never converted), and only from checked
    documents (passed or reviewed): amounts still waiting for review are not counted as spend."""
    with store.conn() as con:
        q = lambda cols, rest='': con.execute(f'SELECT {cols} FROM documents WHERE user_id = %s {rest}', (uid,)).fetchall()
        return {
            'documents': q('count(*) AS n')[0]['n'],
            'by_status': {r['status']: r['n'] for r in q('status, count(*) AS n', 'GROUP BY status')},
            'spend_by_currency': q('currency, sum(total) AS total, count(*) AS n',
                                   "AND total IS NOT NULL AND status IN ('passed', 'reviewed') GROUP BY currency"),
            'top_vendors': q('min(vendor) AS vendor, currency, sum(total) AS total, count(*) AS n',
                             "AND vendor IS NOT NULL AND status IN ('passed', 'reviewed') GROUP BY lower(vendor), currency "
                             'ORDER BY total DESC NULLS LAST LIMIT 10'),
            'by_month': q("to_char(issue_date, 'YYYY-MM') AS month, currency, sum(total) AS total, count(*) AS n",
                          "AND issue_date IS NOT NULL AND status IN ('passed', 'reviewed') GROUP BY month, currency ORDER BY month"),
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
    keeps its zeros). Text starting with = + - @ gets a leading ' so a spreadsheet never runs it as a formula."""
    if v is None:
        return None
    if column in NUMERIC:
        return float(v)
    if isinstance(v, str) and v[:1] in ('=', '+', '-', '@'):
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
            lines = [(i.description, i.amount - (i.discount or 0)) for i in d.items if i.amount is not None]
            lines += [(name, v) for name, v in (('Service charge', d.service_charge), ('Tax', d.tax),
                                                ('Discount', -d.discount if d.discount else None)) if v]
            if not lines or sum(v for _, v in lines) != d.total:
                lines = [('Total', d.total)]
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
        raise HTTPException(422, 'format must be csv, xlsx or quickbooks')
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
            ws.append(cells(cols, row_))
    wb.active.title = 'Documents'
    buf = io.BytesIO()
    wb.save(buf)
    return Response(buf.getvalue(), media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition': 'attachment; filename="documents.xlsx"'})
