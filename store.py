"""SQLite storage for the app: one row per uploaded document, plus the date order confirmed per vendor.
Uploaded files live on disk under storage/ (git-ignored); the database keeps their path."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
STORAGE = ROOT / 'storage'
DB = STORAGE / 'app.db'

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    mime TEXT NOT NULL,
    status TEXT NOT NULL,          -- processing / passed / needs_review / failed / reviewed
    document TEXT,                 -- extracted (or corrected) Document as JSON
    checks TEXT,                   -- failed checks as JSON list
    error TEXT,
    vendor TEXT, currency TEXT, issue_date TEXT, total REAL,   -- copies for search and dashboard
    model TEXT, prompt_version TEXT, seconds REAL, tokens_in INTEGER, tokens_out INTEGER,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS vendor_settings (
    vendor TEXT PRIMARY KEY,       -- lower-case vendor name
    date_order TEXT NOT NULL CHECK (date_order IN ('MDY', 'DMY'))
);
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def connect(db=None):
    """New connection with rows as dicts. One per request keeps SQLite thread-safe in FastAPI."""
    db = Path(db or DB)
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def row(r):
    """sqlite Row to a plain dict with JSON columns decoded."""
    if r is None:
        return None
    d = dict(r)
    for k in ('document', 'checks'):
        d[k] = json.loads(d[k]) if d[k] else None
    return d


def date_order(con, vendor):
    if not vendor:
        return None
    r = con.execute('SELECT date_order FROM vendor_settings WHERE vendor = ?', (vendor.strip().lower(),)).fetchone()
    return r['date_order'] if r else None


def set_date_order(con, vendor, order):
    con.execute('INSERT INTO vendor_settings (vendor, date_order) VALUES (?, ?) '
                'ON CONFLICT(vendor) DO UPDATE SET date_order = excluded.date_order', (vendor.strip().lower(), order))
    con.commit()
