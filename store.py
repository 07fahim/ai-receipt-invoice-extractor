"""PostgreSQL storage for the app (Supabase or any Postgres): one row per uploaded document, plus the date
order confirmed per vendor. Connection string comes from DATABASE_URL in .env; APP_SCHEMA picks the schema
(default 'app', kept out of Supabase's public Data API; tests use their own schema)."""
import os
from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
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
CREATE INDEX IF NOT EXISTS documents_vendor ON documents (lower(vendor));
CREATE INDEX IF NOT EXISTS documents_status ON documents (status);
CREATE TABLE IF NOT EXISTS vendor_settings (
    vendor TEXT PRIMARY KEY,       -- lower-case vendor name
    date_order TEXT NOT NULL CHECK (date_order IN ('MDY', 'DMY'))
);
"""

_pool = None


def schema_name():
    name = os.environ.get('APP_SCHEMA', 'app')  # not 'public': Supabase's Data API only exposes public by default
    assert name.replace('_', '').isalnum(), name  # used inside SQL text below
    return name


def pool():
    """One connection pool per process; creates the schema and tables on first use."""
    global _pool
    if _pool is None:
        name = schema_name()

        def configure(con):
            con.execute(f'SET search_path TO {name}')
            con.commit()

        _pool = ConnectionPool(os.environ['DATABASE_URL'], min_size=1, max_size=5, configure=configure,
                               kwargs={'row_factory': dict_row}, open=True)
        with _pool.connection() as con:
            con.execute(f'CREATE SCHEMA IF NOT EXISTS {name}')
            con.execute(f'SET search_path TO {name}')
            con.execute(SCHEMA)
    return _pool


@contextmanager
def conn():
    """A pooled connection; commits when the block ends without an error."""
    with pool().connection() as con:
        yield con


def date_order(con, vendor):
    if not vendor:
        return None
    r = con.execute('SELECT date_order FROM vendor_settings WHERE vendor = %s', (vendor.strip().lower(),)).fetchone()
    return r['date_order'] if r else None


def set_date_order(con, vendor, order):
    con.execute('INSERT INTO vendor_settings (vendor, date_order) VALUES (%s, %s) '
                'ON CONFLICT (vendor) DO UPDATE SET date_order = excluded.date_order', (vendor.strip().lower(), order))
