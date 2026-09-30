"""PostgreSQL storage for the app (Supabase or any Postgres): one row per uploaded document, plus the date
order each user confirmed per vendor. Every row belongs to a Supabase Auth user (user_id). Connection string comes from DATABASE_URL in .env; APP_SCHEMA picks the schema
(default 'app', kept out of Supabase's public Data API; tests use their own schema)."""
import os
import re
import threading
from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id UUID,                  -- Supabase Auth user; rows without one are visible to nobody
    file_name TEXT NOT NULL,
    mime TEXT NOT NULL,
    file BYTEA NOT NULL,           -- ponytail: files in the database (demo scale, survives redeploys); Supabase Storage if it grows
    status TEXT NOT NULL CHECK (status IN ('processing', 'passed', 'needs_review', 'failed', 'reviewed')),
    document JSONB,                -- extracted (or corrected) Document
    checks JSONB,                  -- failed checks
    error TEXT,
    vendor TEXT, currency TEXT, issue_date DATE, total NUMERIC(18, 2),   -- copies for search and dashboard
    model TEXT, prompt_version TEXT, tokens_in INTEGER, tokens_out INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS user_id UUID;   -- tables created before accounts existed
CREATE INDEX IF NOT EXISTS documents_user ON documents (user_id, id);
CREATE INDEX IF NOT EXISTS documents_vendor ON documents (user_id, lower(vendor));
CREATE INDEX IF NOT EXISTS documents_status ON documents (status);
CREATE TABLE IF NOT EXISTS vendor_date_orders (
    user_id UUID NOT NULL,
    vendor TEXT NOT NULL,          -- vendor_key(): lower case, no punctuation or trailing Ltd/Inc/...
    date_order TEXT NOT NULL CHECK (date_order IN ('MDY', 'DMY')),
    PRIMARY KEY (user_id, vendor)
);
CREATE TABLE IF NOT EXISTS reads (   -- one row per model read (upload or retry): the daily limit counts these,
    user_id UUID NOT NULL,            -- so deleting documents does not give the quota back
    at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS reads_user ON reads (user_id, at);
"""

_pool = None
_pool_lock = threading.Lock()


def schema_name():
    name = os.environ.get('APP_SCHEMA', 'app')  # not 'public': Supabase's Data API only exposes public by default
    if not name.replace('_', '').isalnum():  # used inside SQL text below
        raise ValueError(f'invalid schema name: {name!r}')
    return name


def pool():
    """One connection pool per process; creates the schema and tables on first use."""
    global _pool
    with _pool_lock:  # two first requests at once must not build two pools
        if _pool is None:
            _pool = _open_pool()
    return _pool


def _open_pool():
    """Create the pool, then the schema and tables."""
    name = schema_name()

    def configure(con):
        con.execute(f'SET search_path TO {name}')
        con.commit()

    # prepare_threshold=None: no server-side prepared statements, so a transaction-mode pooler also works;
    # check: drop connections the pooler closed while idle. max_size 10 of the pooler's free-tier limit.
    new = ConnectionPool(os.environ['DATABASE_URL'], min_size=1, max_size=10, configure=configure,
                         check=ConnectionPool.check_connection,
                         kwargs={'row_factory': dict_row, 'prepare_threshold': None}, open=True)
    with new.connection() as con:
        con.execute(f'CREATE SCHEMA IF NOT EXISTS {name}')
        con.execute(f'SET search_path TO {name}')
        con.execute(SCHEMA)
    return new


@contextmanager
def conn():
    """A pooled connection; commits when the block ends without an error."""
    with pool().connection() as con:
        yield con


COMPANY_SUFFIXES = {'ltd', 'limited', 'llc', 'inc', 'co', 'corp', 'corporation', 'company', 'pvt', 'private', 'plc'}


def vendor_key(name):
    """One vendor however it is printed: case, punctuation and trailing company words ignored
    ('SHWAPNO', 'Shwapno Ltd.' and 'Shwapno Limited' are all 'shwapno')."""
    words = re.sub(r'[\W_]+', ' ', (name or '').lower()).split()
    while len(words) > 1 and words[-1] in COMPANY_SUFFIXES:
        words.pop()
    return ' '.join(words)


def date_order(con, user_id, vendor):
    if not vendor_key(vendor):
        return None
    r = con.execute('SELECT date_order FROM vendor_date_orders WHERE user_id = %s AND vendor = %s',
                    (user_id, vendor_key(vendor))).fetchone()
    return r['date_order'] if r else None


def same_number(number):
    """Invoice number for comparing: letters and digits only, lower case ('INV-1042' = 'inv 1042' = '#INV1042')."""
    return re.sub(r'[\W_]', '', (number or '').lower())


def duplicate_of(con, user_id, doc, before_id=None):
    """The earliest of the user's documents with the same vendor, invoice number and total; None if there is none.
    before_id: only documents uploaded before this one, so the first copy stays clean and later copies are flagged.
    ponytail: exact match after clean-up; fuzzy matching would flag INV-1042 against INV-1043."""
    number = same_number(doc.doc_number)
    if not (number and vendor_key(doc.vendor) and doc.total is not None):
        return None
    rows = con.execute(
        "SELECT id, vendor, document->>'doc_number' AS doc_number FROM documents "
        "WHERE user_id = %s AND total = %s AND id < %s AND status IN ('passed', 'needs_review', 'reviewed') "
        "AND regexp_replace(lower(document->>'doc_number'), '[^[:alnum:]]', '', 'g') = %s ORDER BY id",
        (user_id, doc.total, before_id or 2 ** 62, number)).fetchall()
    return next((r for r in rows if vendor_key(r['vendor']) == vendor_key(doc.vendor)), None)


def set_date_order(con, user_id, vendor, order):
    con.execute('INSERT INTO vendor_date_orders (user_id, vendor, date_order) VALUES (%s, %s, %s) '
                'ON CONFLICT (user_id, vendor) DO UPDATE SET date_order = excluded.date_order',
                (user_id, vendor_key(vendor), order))
