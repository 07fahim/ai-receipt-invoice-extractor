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
    file BYTEA NOT NULL,           -- files kept in the database (demo scale, survives redeploys); move to Supabase Storage if it grows
    status TEXT NOT NULL CHECK (status IN ('processing', 'passed', 'needs_review', 'failed', 'reviewed')),
    document JSONB,                -- extracted (or corrected) Document
    checks JSONB,                  -- failed checks
    error TEXT,
    vendor TEXT, currency TEXT, issue_date DATE, total NUMERIC(20, 6),   -- copies for search and dashboard
    model TEXT, prompt_version TEXT, tokens_in INTEGER, tokens_out INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS user_id UUID;   -- tables created before accounts existed
ALTER TABLE documents ALTER COLUMN total TYPE NUMERIC(20, 6);  -- was (18, 2): 3-decimal currencies lost a digit
ALTER TABLE documents ADD COLUMN IF NOT EXISTS extracted JSONB; -- the AI's reading as first saved, kept when the user corrects it
ALTER TABLE documents ADD COLUMN IF NOT EXISTS second_reading JSONB;          -- a second model's reading of a flagged document
ALTER TABLE documents ADD COLUMN IF NOT EXISTS second_read_at TIMESTAMPTZ;    -- when it was asked (failed asks count toward the cap)
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
CREATE TABLE IF NOT EXISTS second_reads (   -- one row per second reading asked for: both caps count these, so
    user_id UUID,                            -- deleting documents does not give quota back (NULL once the account is deleted)
    at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS second_reads_at ON second_reads (at);
CREATE INDEX IF NOT EXISTS second_reads_user ON second_reads (user_id, at);
CREATE TABLE IF NOT EXISTS webhooks (      -- the user's own address for document events (Account page)
    user_id UUID PRIMARY KEY,
    url TEXT NOT NULL,                    -- url and secret encrypted with WEBHOOK_KEY
    secret TEXT NOT NULL,
    last_at TIMESTAMPTZ, last_error TEXT, -- last delivery: when, and why it failed (NULL: it worked)
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS webhook_events (   -- waiting to be sent; deleted once sent, so restarts lose nothing
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id UUID NOT NULL,
    payload JSONB NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS webhook_events_user ON webhook_events (user_id, id);
CREATE TABLE IF NOT EXISTS assistant_chats (   -- kept until the user deletes them
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id UUID NOT NULL,
    title TEXT NOT NULL,
    messages JSONB NOT NULL DEFAULT '[]',     -- [{role, content, steps?}]
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS assistant_chats_user ON assistant_chats (user_id, updated_at);
CREATE TABLE IF NOT EXISTS assistant_messages (   -- one row per answered message: the caps count these, so deleting
    user_id UUID,                                  -- a chat does not give quota back (NULL once the account is deleted)
    at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS assistant_messages_at ON assistant_messages (at);
CREATE INDEX IF NOT EXISTS assistant_messages_user ON assistant_messages (user_id, at);
"""

_pool = None
_pool_lock = threading.Lock()


def schema_name():
    name = os.environ.get('APP_SCHEMA', 'app')  # not 'public': Supabase's Data API only exposes public by default
    if not name.replace('_', '').isalnum():  # used inside SQL text below
        raise ValueError(f'invalid schema name: {name!r}')
    return name


def pool():
    global _pool
    with _pool_lock:  # two first requests at once must not build two pools
        if _pool is None:
            _pool = _open_pool()
    return _pool


def _open_pool():
    name = schema_name()

    def configure(con):
        con.execute(f'SET search_path TO {name}')
        con.commit()

    # prepare_threshold=None: no server-side prepared statements, so a transaction-mode pooler also works;
    # check: drop connections the pooler closed while idle. max_size 5: the free pooler's client limit is
    # shared with n8n and any local API on the same database.
    new = ConnectionPool(os.environ['DATABASE_URL'], min_size=1, max_size=5, configure=configure,
                         check=ConnectionPool.check_connection,
                         kwargs={'row_factory': dict_row, 'prepare_threshold': None}, open=True)
    with new.connection() as con:
        con.execute(f'CREATE SCHEMA IF NOT EXISTS {name}')
        con.execute(f'SET search_path TO {name}')
        con.execute(SCHEMA)
    return new


@contextmanager
def conn():
    with pool().connection() as con:
        yield con


COMPANY_SUFFIXES = {'ltd', 'limited', 'llc', 'inc', 'co', 'corp', 'corporation', 'company', 'pvt', 'private', 'plc'}


def vendor_key(name):
    # 'SHWAPNO', 'Shwapno Ltd.' and 'Shwapno Limited' are all 'shwapno'
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
    # 'INV-1042' = 'inv 1042' = '#INV1042'
    return re.sub(r'[\W_]', '', (number or '').lower())


def duplicate_of(con, user_id, doc, before_id=None):
    # before_id: the first copy stays clean, later copies are flagged
    # Exact match after clean-up: fuzzy matching would flag INV-1042 against INV-1043.
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
