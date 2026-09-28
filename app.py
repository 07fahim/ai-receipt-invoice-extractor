"""Receipt & Invoice Extractor API.

Run:  uvicorn app:app --reload        (docs at http://127.0.0.1:8000/docs)
Needs DATABASE_URL (PostgreSQL, e.g. Supabase session pooler) and GEMINI_API_KEY in .env.
Optional WEBHOOK_URL (+ WEBHOOK_SECRET): each passed or reviewed document is sent there, e.g. to n8n.
Upload -> background extraction (vision LLM) -> checks -> review/correct -> history, stats, export.
"""
import csv
import hashlib
import hmac
import io
import json
import os
import threading
import time
import urllib.request

import pypdfium2
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, UploadFile
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

app = FastAPI(title='Receipt & Invoice Extractor')


def get_row(con, doc_id, with_file=False):
    cols = '*' if with_file else 'id, file_name, mime, status, document, checks, error, vendor, currency, issue_date, ' \
                                 'total, model, prompt_version, tokens_in, tokens_out, created_at, updated_at'
    r = con.execute(f'SELECT {cols} FROM documents WHERE id = %s', (doc_id,)).fetchone()
    if r is None:
        raise HTTPException(404, 'document not found')
    return r


def save(con, doc_id, doc: Document, status, extra=None):
    """Store a document with its checks. The vendor's confirmed date order is applied first."""
    order = store.date_order(con, doc.vendor)
    doc = apply_date_order(doc, order)
    checks = validate(doc, date_order=order)
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
        r = get_row(con, doc_id)
    body = json.dumps({'event': f'document.{r["status"]}', 'id': r['id'], 'file_name': r['file_name'],
                       'status': r['status'], 'document': r['document'], 'checks': r['checks']}).encode()
    headers = {'Content-Type': 'application/json', 'User-Agent': 'receipt-extractor/0.1'}
    secret = os.environ.get('WEBHOOK_SECRET')
    if secret:
        headers['X-Signature'] = 'sha256=' + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    for attempt in range(3):  # ponytail: in-process retries; a queue if deliveries must survive restarts
        try:
            with urllib.request.urlopen(urllib.request.Request(url, body, headers), timeout=10):
                return
        except Exception as e:
            print(f'webhook for document {doc_id} failed (attempt {attempt + 1}): {e}')
            time.sleep(2 ** attempt)


def process(doc_id):
    """Background job: send the file to the model, parse, check, store. Failures are stored, never raised."""
    with store.conn() as con:
        data = get_row(con, doc_id, with_file=True)['file']
    try:
        text, tin, tout, _ = providers.call(MODEL, bytes(data))
        doc = providers.parse(text)
        extra = {'model': MODEL, 'prompt_version': hashlib.sha256(providers.PROMPT.encode()).hexdigest()[:8],
                 'tokens_in': tin, 'tokens_out': tout}
        with store.conn() as con:
            save(con, doc_id, doc, None, extra)
            passed = get_row(con, doc_id)['status'] == 'passed'
        if passed:
            send_event(doc_id)
    except Exception as e:
        with store.conn() as con:
            con.execute("UPDATE documents SET status = 'failed', error = %s, updated_at = now() WHERE id = %s",
                        (str(e)[:300], doc_id))


@app.post('/documents', status_code=202)
async def upload(files: list[UploadFile], tasks: BackgroundTasks):
    """Upload up to 20 files (PDF, JPG, PNG, WebP; max 10 MB each). Extraction runs in the background."""
    if not files or len(files) > MAX_FILES:
        raise HTTPException(400, f'send 1 to {MAX_FILES} files')
    created = []
    for f in files:
        data = await f.read(MAX_BYTES + 1)
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
            doc_id = con.execute("INSERT INTO documents (file_name, mime, file, status) VALUES (%s, %s, %s, 'processing') "
                                 'RETURNING id', (os.path.basename(f.filename or 'upload'), kind, data)).fetchone()['id']
        tasks.add_task(process, doc_id)
        created.append({'id': doc_id, 'file_name': f.filename, 'status': 'processing'})
    return created


@app.get('/documents')
def list_documents(status: str | None = None, q: str | None = None, date_from: str | None = None,
                   date_to: str | None = None, limit: int = Query(50, le=200), offset: int = 0):
    """History: newest first. q searches vendor and file name; dates filter on the document's issue date."""
    sql, args = 'SELECT id, file_name, status, vendor, currency, issue_date, total, created_at FROM documents WHERE true', []
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
def get_document(doc_id: int):
    with store.conn() as con:
        return get_row(con, doc_id)


@app.put('/documents/{doc_id}')
def update_document(doc_id: int, doc: Document, tasks: BackgroundTasks):
    """Save the user's corrections. Checks run again; the document is marked reviewed and sent to the webhook."""
    with store.conn() as con:
        get_row(con, doc_id)
        save(con, doc_id, doc, 'reviewed')
    tasks.add_task(send_event, doc_id)
    return get_document(doc_id)


@app.post('/documents/{doc_id}/retry', status_code=202)
def retry(doc_id: int, tasks: BackgroundTasks):
    with store.conn() as con:
        get_row(con, doc_id)
        con.execute("UPDATE documents SET status = 'processing', error = NULL, updated_at = now() WHERE id = %s", (doc_id,))
    tasks.add_task(process, doc_id)
    return {'id': doc_id, 'status': 'processing'}


@app.delete('/documents/{doc_id}', status_code=204)
def delete_document(doc_id: int):
    """Delete the record together with the uploaded file."""
    with store.conn() as con:
        if con.execute('DELETE FROM documents WHERE id = %s', (doc_id,)).rowcount == 0:
            raise HTTPException(404, 'document not found')


@app.get('/documents/{doc_id}/file')
def get_file(doc_id: int):
    with store.conn() as con:
        r = get_row(con, doc_id, with_file=True)
    return Response(bytes(r['file']), media_type=r['mime'],
                    headers={'Content-Disposition': f'inline; filename="{r["file_name"]}"'})


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
def page_count(doc_id: int):
    with store.conn() as con:
        r = get_row(con, doc_id, with_file=True)
    return {'pages': pdf_pages(r['file']) if r['mime'] == 'application/pdf' else 1}


@app.get('/documents/{doc_id}/pages/{n}')
def page_image(doc_id: int, n: int):
    """Page n (from 0) as an image for the review screen. PDFs are rendered; images are returned as is."""
    with store.conn() as con:
        r = get_row(con, doc_id, with_file=True)
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
def set_vendor_date_order(vendor: str, body: DateOrder, tasks: BackgroundTasks):
    """Confirm how this vendor prints dates (MDY or DMY). Unreviewed documents of the vendor are re-checked;
    those that now pass are sent to the webhook."""
    if body.date_order not in ('MDY', 'DMY'):
        raise HTTPException(422, 'date_order must be MDY or DMY')
    with store.conn() as con:
        store.set_date_order(con, vendor, body.date_order)
        rows = con.execute("SELECT id, document FROM documents WHERE lower(vendor) = %s "
                           "AND status = 'needs_review'", (vendor.strip().lower(),)).fetchall()
        for r in rows:
            save(con, r['id'], Document.model_validate(r['document']), None)
            if get_row(con, r['id'])['status'] == 'passed':
                tasks.add_task(send_event, r['id'])
    return {'vendor': vendor, 'date_order': body.date_order, 'rechecked': len(rows)}


@app.get('/stats')
def stats():
    """Dashboard numbers. Money is summed per currency (never converted)."""
    with store.conn() as con:
        q = lambda sql: con.execute(sql).fetchall()
        return {
            'documents': q('SELECT count(*) AS n FROM documents')[0]['n'],
            'by_status': {r['status']: r['n'] for r in q('SELECT status, count(*) AS n FROM documents GROUP BY status')},
            'spend_by_currency': q("SELECT currency, sum(total) AS total, count(*) AS n FROM documents "
                                   "WHERE total IS NOT NULL AND status != 'failed' GROUP BY currency"),
            'top_vendors': q("SELECT min(vendor) AS vendor, currency, sum(total) AS total, count(*) AS n FROM documents "
                             "WHERE vendor IS NOT NULL AND status != 'failed' GROUP BY lower(vendor), currency "
                             "ORDER BY total DESC NULLS LAST LIMIT 10"),
            'by_month': q("SELECT to_char(issue_date, 'YYYY-MM') AS month, currency, sum(total) AS total, count(*) AS n "
                          "FROM documents WHERE issue_date IS NOT NULL AND status != 'failed' "
                          "GROUP BY month, currency ORDER BY month"),
        }


DOC_COLUMNS = ['id', 'file_name', 'status', 'doc_type', 'vendor', 'buyer', 'doc_number', 'issue_date', 'due_date',
               'currency', 'subtotal', 'discount', 'tax', 'service_charge', 'total']
ITEM_COLUMNS = ['document_id', 'description', 'quantity', 'unit_price', 'amount', 'discount']


def export_rows(status):
    """(document rows, item rows) for export; failed documents are left out."""
    sql, args = "SELECT id, file_name, status, document FROM documents WHERE status != 'failed' AND document IS NOT NULL", []
    if status:
        sql += ' AND status = %s'; args.append(status)
    docs, items = [], []
    with store.conn() as con:
        for r in con.execute(sql + ' ORDER BY id', args):
            d = r['document']
            docs.append([r['id'], r['file_name'], r['status']] + [d.get(k) for k in DOC_COLUMNS[3:]])
            items += [[r['id']] + [i.get(k) for k in ITEM_COLUMNS[1:]] for i in d.get('items') or []]
    return docs, items


def number(v):
    """Money is stored as exact decimal text; spreadsheets get numbers."""
    try:
        return float(v) if isinstance(v, str) and v.replace('.', '', 1).lstrip('-').isdigit() else v
    except ValueError:
        return v


@app.get('/export')
def export(format: str = 'xlsx', status: str | None = None):
    """Download documents as CSV (one row per document) or XLSX (Documents and Items sheets)."""
    if format not in ('csv', 'xlsx'):
        raise HTTPException(422, 'format must be csv or xlsx')
    docs, items = export_rows(status)
    if format == 'csv':
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(DOC_COLUMNS)
        w.writerows(docs)
        return Response(buf.getvalue().encode('utf-8-sig'), media_type='text/csv',
                        headers={'Content-Disposition': 'attachment; filename="documents.csv"'})
    from openpyxl import Workbook
    wb = Workbook()
    for ws, cols, rows in ((wb.active, DOC_COLUMNS, docs), (wb.create_sheet('Items'), ITEM_COLUMNS, items)):
        ws.append(cols)
        for row_ in rows:
            ws.append([number(v) for v in row_])
    wb.active.title = 'Documents'
    buf = io.BytesIO()
    wb.save(buf)
    return Response(buf.getvalue(), media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition': 'attachment; filename="documents.xlsx"'})
