from collections import Counter
from decimal import Decimal

from schema import Document
from validate import review, validate

FIELDS = ['doc_type', 'vendor', 'branch', 'buyer', 'doc_number', 'issue_date', 'due_date', 'currency',
          'subtotal', 'discount', 'tax', 'service_charge', 'total']
ITEM_FIELDS = ['description', 'quantity', 'unit_price', 'amount', 'discount']


def same(a, b):
    if isinstance(a, Decimal) or isinstance(b, Decimal):
        return a == b if a is None or b is None else Decimal(a) == Decimal(b)
    a, b = (str(v).strip() if v is not None else '' for v in (a, b))
    return a == b


def changed(first: Document, saved: Document) -> list[str]:
    out = [f for f in FIELDS if not same(getattr(first, f), getattr(saved, f))]
    lines = lambda d: [[getattr(i, f) for f in ITEM_FIELDS] for i in d.items]
    a, b = lines(first), lines(saved)
    if len(a) != len(b) or any(not same(x, y) for la, lb in zip(a, b) for x, y in zip(la, lb)):
        out.append('items')
    return out


def report(rows):
    fields, corrected, missed = Counter(), 0, 0
    for first_json, saved_json in rows:
        first, saved = Document.model_validate(first_json), Document.model_validate(saved_json)
        diff = changed(first, saved)
        if diff:
            corrected += 1
            fields.update(diff)
            if not review(validate(first)):  # checks re-run with today's rules, not those at reading time
                missed += 1
    n = len(rows)
    lines = [f'{n} reviewed documents, {corrected} corrected' + (f' ({corrected / n:.0%})' if n else '')]
    if corrected:
        lines.append(f'{missed} of the corrected ones had passed every check (mistakes the checks missed)')
        lines.append('Fields changed: ' + ', '.join(f'{f} {c}' for f, c in fields.most_common()))
    return lines


if __name__ == '__main__':
    import providers
    providers.load_env()
    import store
    with store.conn() as con:
        rows = con.execute("SELECT extracted, document FROM documents WHERE status = 'reviewed' "
                           'AND extracted IS NOT NULL AND document IS NOT NULL').fetchall()
    print('\n'.join(report([(r['extracted'], r['document']) for r in rows])))
