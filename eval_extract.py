"""M3: extraction accuracy of vision LLMs on CORD-v2.

python eval_extract.py MODEL [SPLIT] [LIMIT] [PROMPT_VERSION]     e.g.  python eval_extract.py gemini-3.5-flash-lite test 10
PROMPT_VERSION re-scores cached answers of an older prompt without calling the API (0 for no limit).
SPLIT: test / validation (CORD receipts) or invoices_test / invoices_validation / invoices_train (katanaml invoices).
The katanaml invoices are US format, so 'issue_date with vendor order' re-reads printed dates as MDY,
like a user confirming the vendor's date format once in the app.
Raw model responses are cached in data/llm_cache/<model>/<prompt version>/ so a rerun costs no quota
and a changed prompt never reuses old answers.
Writes results/extract_<model>_<split>.json.
"""
import hashlib
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
from validate import apply_date_order, validate

ROOT = Path(__file__).parent
HEADER = ('subtotal', 'tax', 'service_charge', 'discount', 'total')
TEXT = ('doc_number', 'issue_date', 'vendor', 'buyer', 'currency')


def same(a, b, field=''):
    """Money equal to the cent. Only a discount may differ in sign (a convention, not an error)."""
    if a is None or b is None:
        return False
    if field == 'discount':
        a, b = abs(a), abs(b)
    return abs(a - b) < 0.005


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
    include the address, so a name of 4+ characters only has to be the start of the label."""
    if p is None:
        return False
    if field in ('issue_date', 'currency'):
        return str(p).upper() == str(g).upper()
    p, g = (''.join(str(x).casefold().split()) for x in (p, g))
    if field == 'doc_number' or not g:
        return p == g
    return p == g or (len(p) >= 4 and g.startswith(p))


def score(pred, gold):
    """Per-field correctness for the fields the ground truth has."""
    s = {f: same(getattr(pred, f), getattr(gold, f), f) for f in HEADER if getattr(gold, f) is not None}
    s.update({f: text_match(f, getattr(pred, f), getattr(gold, f)) for f in TEXT if getattr(gold, f) is not None})
    s['item_amounts_f1'] = f1([i.amount for i in pred.items if i.amount is not None],
                              [i.amount for i in gold.items if i.amount is not None])
    s['item_names_f1'] = name_f1([i.description for i in pred.items], [i.description for i in gold.items])
    s['all_correct'] = all(v for k, v in s.items() if k in HEADER + TEXT) and s['item_amounts_f1'] == 1.0
    return s


def rate(vals):
    return {'rate': round(statistics.mean(vals), 4), 'n': len(vals)} if vals else None


def run_model(name, image, cache, cache_only=False):
    if cache.exists():
        return json.loads(cache.read_text(encoding='utf8'))
    if cache_only:
        return {'text': None, 'in': None, 'out': None, 'seconds': 0, 'error': 'not in cache'}
    t = time.perf_counter()
    try:
        text, tin, tout, attempts = providers.call(name, image)
        rec = {'text': text, 'in': tin, 'out': tout, 'attempts': attempts, 'error': None}
    except Exception as e:  # recorded and counted as a failed extraction
        rec = {'text': None, 'in': None, 'out': None, 'error': str(e)[:300]}
    rec['seconds'] = round(time.perf_counter() - t, 2)
    if rec['error'] is None:  # failed calls are not cached, so a rerun retries them
        cache.write_text(json.dumps(rec, ensure_ascii=False), encoding='utf8')
    time.sleep(providers.MODELS[name][4])
    return rec


def main(name, split='test', limit=None, prompt_version=None):
    providers.load_env()
    cache_only = prompt_version is not None
    prompt_version = prompt_version or hashlib.sha256(providers.PROMPT.encode()).hexdigest()[:8]
    limit = int(limit) if limit and int(limit) > 0 else None
    date_order = 'MDY' if split.startswith('invoices_') else None  # katanaml invoices are US format
    cache_dir = ROOT / 'data' / 'llm_cache' / name.replace('/', '_') / prompt_version
    cache_dir.mkdir(parents=True, exist_ok=True)
    if split.startswith('invoices_'):
        docs = list(invoices.load(split.removeprefix('invoices_')))
    else:
        docs = [(i, img, cord.to_document(p)) for i, img, p, _ in cord.load(ROOT / 'data' / f'cord_v2_{split}.parquet')]
    docs = docs[:limit]
    if not docs:
        raise SystemExit('no documents to evaluate')

    rows = []
    for doc_id, image, gold in docs:
        rec = run_model(name, image, cache_dir / f'{split}_{doc_id}.json', cache_only)
        row = {'id': doc_id, 'seconds': rec['seconds'], 'in': rec['in'], 'out': rec['out'],
               'attempts': rec.get('attempts'), 'error': rec['error']}
        if rec['error'] is None:
            try:
                pred = providers.parse(rec['text'])
                row['score'] = score(pred, gold)
                row['flagged'] = [i['check'] for i in validate(pred)]
                if gold.issue_date is not None and date_order:
                    row['date_ok_with_vendor_order'] = apply_date_order(pred, date_order).issue_date == gold.issue_date
                    row['date_flagged_ambiguous'] = 'date_ambiguous' in row['flagged']
                    row['date_wrong_raw'] = not row['score'].get('issue_date', True)
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
        'model': name, 'prompt_version': prompt_version, 'split': split, 'docs': len(rows),
        'failed_calls_or_invalid_json': len(rows) - len(ok),
        'field_accuracy': field,
        'wrong_docs_flagged_by_validation': f'{sum(bool(r["flagged"]) for r in wrong)} / {len(wrong)}',
        'correct_docs_flagged_by_validation': f'{sum(bool(r["flagged"]) for r in right)} / {len(right)}',
        'median_seconds': statistics.median([r['seconds'] for r in rows]),
        'calls_with_retries': sum(1 for r in rows if (r.get('attempts') or 1) > 1),
        'median_tokens_in_out': [statistics.median([r['in'] for r in ok if r['in']] or [0]),
                                 statistics.median([r['out'] for r in ok if r['out']] or [0])],
        'issue_date_with_vendor_order': rate([r['date_ok_with_vendor_order'] for r in ok if 'date_ok_with_vendor_order' in r]),
        'wrong_dates_flagged_ambiguous': f"{sum(r['date_flagged_ambiguous'] for r in ok if r.get('date_wrong_raw'))} / {sum(bool(r.get('date_wrong_raw')) for r in ok)}",
        'errors': sorted(Counter((r['error'] or '')[:80] for r in rows if r['error']).items()),
    }
    out = ROOT / 'results' / f'extract_{name.replace("/", "_")}_{split}{f"_first{limit}" if limit else ""}.json'
    out.write_text(json.dumps({'summary': summary, 'docs': rows}, indent=1, ensure_ascii=False, default=str), encoding='utf8')
    print(json.dumps(summary, indent=1, default=str))


if __name__ == '__main__':
    main(*sys.argv[1:5])
