"""M3: extraction accuracy of vision LLMs on CORD-v2.

python eval_extract.py MODEL [SPLIT] [LIMIT]     e.g.  python eval_extract.py gemini-3.5-flash-lite test 10
SPLIT: test / validation (CORD receipts) or invoices_test / invoices_validation (katanaml invoices).
Raw model responses are cached in data/llm_cache/ so a rerun costs no quota.
Writes results/extract_<model>_<split>.json.
"""
import json
import statistics
import sys
import time
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

import cord
import invoices
import providers
from validate import validate

ROOT = Path(__file__).parent
HEADER = ('subtotal', 'tax', 'service_charge', 'discount', 'total')
TEXT = ('doc_number', 'issue_date', 'vendor', 'buyer', 'currency')


def same(a, b):
    return a is not None and b is not None and abs(abs(a) - abs(b)) < 0.005  # discount sign is a convention


def f1(pred, gold):
    """Multiset F1 of two lists (1.0 when both are empty)."""
    if not pred and not gold:
        return 1.0
    hit = sum((Counter(pred) & Counter(gold)).values())
    return 0.0 if hit == 0 else 2 * hit / (len(pred) + len(gold))


def name_f1(pred, gold):
    """Item names matched one-to-one when at least 80% similar (ignoring case and spaces)."""
    norm = lambda s: ''.join((s or '').casefold().split())
    left, hit = [norm(p) for p in pred], 0
    for g in map(norm, gold):
        best = max(range(len(left)), key=lambda k: SequenceMatcher(None, left[k], g).ratio(), default=None)
        if best is not None and SequenceMatcher(None, left[best], g).ratio() >= 0.8:
            hit += 1
            left.pop(best)
    return 1.0 if not pred and not gold else (0.0 if hit == 0 else 2 * hit / (len(pred) + len(gold)))


def text_match(field, p, g):
    """Dates and currency must be equal. Names and numbers ignore case and spaces; vendor/buyer labels
    include the address, so the name only has to be the start of it."""
    if p is None:
        return False
    if field in ('issue_date', 'currency'):
        return str(p).upper() == str(g).upper()
    p, g = (''.join(str(x).casefold().split()) for x in (p, g))
    return p == g if field == 'doc_number' else bool(p) and (g.startswith(p) or p.startswith(g))


def score(pred, gold):
    """Per-field correctness for the fields the ground truth has."""
    s = {f: same(getattr(pred, f), getattr(gold, f)) for f in HEADER if getattr(gold, f) is not None}
    s.update({f: text_match(f, getattr(pred, f), getattr(gold, f)) for f in TEXT if getattr(gold, f) is not None})
    s['item_amounts_f1'] = f1([i.amount for i in pred.items if i.amount is not None],
                              [i.amount for i in gold.items if i.amount is not None])
    s['item_names_f1'] = name_f1([i.description for i in pred.items], [i.description for i in gold.items])
    s['all_correct'] = all(v for k, v in s.items() if k in HEADER + TEXT) and s['item_amounts_f1'] == 1.0
    return s


def run_model(name, image, cache):
    if cache.exists():
        return json.loads(cache.read_text(encoding='utf8'))
    t = time.perf_counter()
    try:
        text, tin, tout = providers.call(name, image)
        rec = {'text': text, 'in': tin, 'out': tout, 'error': None}
    except Exception as e:  # recorded and counted as a failed extraction
        rec = {'text': None, 'in': None, 'out': None, 'error': str(e)[:300]}
    rec['seconds'] = round(time.perf_counter() - t, 2)
    if rec['error'] is None:  # failed calls are not cached, so a rerun retries them
        cache.write_text(json.dumps(rec, ensure_ascii=False), encoding='utf8')
    time.sleep(providers.MODELS[name][4])
    return rec


def main(name, split='test', limit=None):
    providers.load_env()
    cache_dir = ROOT / 'data' / 'llm_cache' / name.replace('/', '_')
    cache_dir.mkdir(parents=True, exist_ok=True)
    if split.startswith('invoices_'):
        docs = list(invoices.load(split.removeprefix('invoices_')))
    else:
        docs = [(i, img, cord.to_document(p)) for i, img, p, _ in cord.load(ROOT / 'data' / f'cord_v2_{split}.parquet')]
    docs = docs[:int(limit) if limit else None]

    rows = []
    for doc_id, image, gold in docs:
        rec = run_model(name, image, cache_dir / f'{split}_{doc_id}.json')
        row = {'id': doc_id, 'seconds': rec['seconds'], 'in': rec['in'], 'out': rec['out'], 'error': rec['error']}
        if rec['error'] is None:
            try:
                pred = providers.parse(rec['text'])
                row['score'] = score(pred, gold)
                row['flagged'] = [i['check'] for i in validate(pred)]
            except Exception as e:
                row['error'] = f'parse: {str(e)[:200]}'
        rows.append(row)
        print(doc_id, row.get('error') or ('ok' if row['score']['all_correct'] else 'wrong'), flush=True)

    ok = [r for r in rows if not r['error']]
    field = {}
    for f in HEADER + TEXT + ('item_amounts_f1', 'item_names_f1', 'all_correct'):
        vals = [r['score'][f] for r in ok if f in r['score']]
        if vals:
            field[f] = {'rate': round(statistics.mean(vals), 4), 'n': len(vals)}
    wrong = [r for r in ok if not r['score']['all_correct']]
    right = [r for r in ok if r['score']['all_correct']]
    summary = {
        'model': name, 'split': split, 'docs': len(rows),
        'failed_calls_or_invalid_json': len(rows) - len(ok),
        'field_accuracy': field,
        'wrong_docs_flagged_by_validation': f'{sum(bool(r["flagged"]) for r in wrong)} / {len(wrong)}',
        'correct_docs_flagged_by_validation': f'{sum(bool(r["flagged"]) for r in right)} / {len(right)}',
        'median_seconds': statistics.median([r['seconds'] for r in rows]),
        'median_tokens_in_out': [statistics.median([r['in'] for r in ok if r['in']] or [0]),
                                 statistics.median([r['out'] for r in ok if r['out']] or [0])],
        'errors': sorted(Counter((r['error'] or '')[:80] for r in rows if r['error']).items()),
    }
    out = ROOT / 'results' / f'extract_{name.replace("/", "_")}_{split}.json'
    out.write_text(json.dumps({'summary': summary, 'docs': rows}, indent=1, ensure_ascii=False, default=str), encoding='utf8')
    print(json.dumps(summary, indent=1, default=str))


if __name__ == '__main__':
    main(*sys.argv[1:4])
