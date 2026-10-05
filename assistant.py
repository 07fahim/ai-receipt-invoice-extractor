import json
from datetime import date

from fastapi import HTTPException

STATUSES = {'passed', 'needs_review', 'reviewed', 'failed'}
CHECKED = "AND status IN ('passed', 'reviewed')"   # money totals use checked documents only, like the dashboard

TOOLS = [
    {'type': 'function', 'function': {
        'name': 'search_documents',
        'description': 'List the user\'s documents, newest first. All filters are optional.',
        'parameters': {'type': 'object', 'properties': {
            'vendor': {'type': 'string', 'description': 'part of the vendor name'},
            'date_from': {'type': 'string', 'description': 'YYYY-MM-DD, issue date on or after'},
            'date_to': {'type': 'string', 'description': 'YYYY-MM-DD, issue date on or before'},
            'status': {'type': 'string', 'enum': sorted(STATUSES)},
            'currency': {'type': 'string', 'description': 'ISO code, e.g. BDT'},
            'limit': {'type': 'integer', 'description': 'at most 20'}}}}},
    {'type': 'function', 'function': {
        'name': 'spend_summary',
        'description': 'Total spend and document count per vendor, month or currency. Only checked documents '
                       '(passed or reviewed). Totals are per currency, never converted.',
        'parameters': {'type': 'object', 'required': ['group_by'], 'properties': {
            'group_by': {'type': 'string', 'enum': ['vendor', 'month', 'currency']},
            'date_from': {'type': 'string', 'description': 'YYYY-MM-DD'},
            'date_to': {'type': 'string', 'description': 'YYYY-MM-DD'}}}}},
    {'type': 'function', 'function': {
        'name': 'get_document',
        'description': 'One document: fields, line items, the checks that failed with their reasons, a suggested fix, '
                       'and where a second AI reading differs.',
        'parameters': {'type': 'object', 'required': ['id'], 'properties': {'id': {'type': 'integer'}}}}},
    {'type': 'function', 'function': {
        'name': 'due_bills',
        'description': 'Documents with a due date from today to today + days.',
        'parameters': {'type': 'object', 'required': ['days'], 'properties': {
            'days': {'type': 'integer', 'description': '1 to 90'}}}}},
    {'type': 'function', 'function': {
        'name': 'search_items',
        'description': 'Find documents whose vendor or a line item contains any of the words, e.g. "latte" or '
                       '"printer ink". Try other words for the same thing if nothing is found.',
        'parameters': {'type': 'object', 'required': ['text'], 'properties': {'text': {'type': 'string'}}}}},
]


def day(value):
    return None if value is None else date.fromisoformat(value)  # 'last week' raises ValueError


def search_documents(con, uid, vendor=None, date_from=None, date_to=None, status=None, currency=None, limit=20):
    if status is not None and status not in STATUSES:
        raise ValueError(f'status must be one of {sorted(STATUSES)}')
    sql, args = 'SELECT id, vendor, issue_date, total, currency, status FROM documents WHERE user_id = %s', [uid]
    for cond, value in (('vendor ILIKE %s', vendor and f'%{like(vendor)}%'), ('issue_date >= %s', day(date_from)),
                        ('issue_date <= %s', day(date_to)), ('status = %s', status),
                        ('upper(currency) = upper(%s)', currency)):
        if value is not None:
            sql += f' AND {cond}'; args.append(value)
    return con.execute(sql + ' ORDER BY id DESC LIMIT %s', (*args, max(1, min(int(limit), 20)))).fetchall()


def spend_summary(con, uid, group_by, date_from=None, date_to=None):
    cols = {'vendor': ('min(vendor) AS vendor, currency', 'lower(vendor), currency'),
            'month': ("to_char(issue_date, 'YYYY-MM') AS month, currency", "to_char(issue_date, 'YYYY-MM'), currency"),
            'currency': ('currency', 'currency')}
    if group_by not in cols:
        raise ValueError('group_by must be vendor, month or currency')
    select, group = cols[group_by]
    sql, args = f'SELECT {select}, sum(total) AS total, count(*) AS n FROM documents WHERE user_id = %s {CHECKED} AND total IS NOT NULL', [uid]
    for cond, value in (('issue_date >= %s', day(date_from)), ('issue_date <= %s', day(date_to))):
        if value is not None:
            sql += f' AND {cond}'; args.append(value)
    return con.execute(f'{sql} GROUP BY {group} ORDER BY total DESC LIMIT 50', args).fetchall()


def get_document(con, uid, id):
    import app  # here, not at the top: app imports this module
    r = app.get_document(int(id), uid)
    return {k: r[k] for k in ('id', 'file_name', 'status', 'document', 'checks', 'suggestion', 'second_reading')}


def due_bills(con, uid, days):
    if not 1 <= int(days) <= 90:
        raise ValueError('days must be 1 to 90')
    return con.execute(
        "SELECT id, vendor, (document->>'due_date')::date AS due_date, total, currency, status FROM documents "
        "WHERE user_id = %s AND status != 'failed' AND (document->>'due_date')::date BETWEEN current_date AND current_date + %s "
        'ORDER BY due_date', (uid, int(days))).fetchall()


def like(text):
    return text.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')  # the words match as typed


def search_items(con, uid, text):
    words = [f'%{like(w)}%' for w in str(text).split()[:5]]
    if not words:
        raise ValueError('text is empty')
    items = "jsonb_array_elements(coalesce(document->'items', '[]'::jsonb)) i WHERE i->>'description' ILIKE ANY(%s)"
    return con.execute(
        f'SELECT id, vendor, issue_date, total, currency, status, '
        f"(SELECT coalesce(array_agg(i->>'description'), '{{}}') FROM {items}) AS matches "
        f'FROM documents WHERE user_id = %s AND document IS NOT NULL '
        f'AND (vendor ILIKE ANY(%s) OR EXISTS (SELECT 1 FROM {items})) ORDER BY id DESC LIMIT 20',
        (words, uid, words, words)).fetchall()


FUNCTIONS = {f.__name__: f for f in (search_documents, spend_summary, get_document, due_bills, search_items)}


def run_tool(con, uid, name, args):
    # any mistake goes back to the model as the result, so it can try again
    try:
        if name not in FUNCTIONS:
            raise ValueError(f'unknown tool {name}')
        if not isinstance(args, dict):
            raise ValueError('arguments must be a JSON object')
        result = FUNCTIONS[name](con, uid, **args)
    except HTTPException as e:
        result = {'error': e.detail}
    except (TypeError, ValueError, LookupError) as e:
        result = {'error': str(e)}
    return json.dumps(result, default=str)
