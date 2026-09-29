"""Experiment: does a second, targeted reading fix documents that failed a check?

python eval_reread.py        (the flagged 9edae16b invoice test runs: clean, very_bad_photo, rot90)
Each flagged document gets one more call with the failed checks as a hint. Counted, with the answer key:
fixed (was wrong, now fully correct), still_flagged (still wrong, still caught), silenced (still wrong but now passes
every check: the dangerous case), broken (was correct, now wrong), kept (was correct, still correct).
Dates are re-read as MDY first (the user confirms a vendor's date format once), so only reading errors count.
Answers are cached in data/llm_cache/<model>/<prompt version>/reread/.
"""
import hashlib
import json
from pathlib import Path

import invoices
import providers
from eval_extract import damage, score
from validate import apply_date_order, validate

ROOT = Path(__file__).parent
MODEL = 'gemini-3.1-flash-lite'
# checks a closer look can fix; an ambiguous date, a duplicate or several documents in one file cannot be re-read away
READING_CHECKS = {'items_sum', 'total_math', 'items_total', 'line_math', 'total_format', 'total_present', 'items_missing'}


def reread_prompt(checks):
    problems = '\n'.join(f'- {c["message"]}' for c in checks)
    return (providers.PROMPT + '\n\nA first reading of this document failed these checks:\n' + problems +
            '\nLook at the document again, especially those numbers, and return the corrected JSON. Copy every '
            'value exactly as printed. Never change a value just to make the numbers add up: if the document '
            'itself does not add up, keep what is printed.')


def main():
    providers.load_env()
    version = hashlib.sha256(providers.PROMPT.encode()).hexdigest()[:8]
    cache = ROOT / 'data' / 'llm_cache' / MODEL / version
    (cache / 'reread').mkdir(parents=True, exist_ok=True)
    images = {i: (img, gold) for i, img, gold in invoices.load('test')}
    counts, details = {}, []
    for variant in ('', 'very_bad_photo', 'rot90'):
        suffix = f'_{variant}' if variant else ''
        for d in json.load(open(ROOT / 'results' / f'extract_{MODEL}_invoices_test{suffix}_p{version}.json', encoding='utf8'))['docs']:
            if d.get('error') or not set(d['flagged']) & READING_CHECKS:
                continue
            img, gold = images[d['id']]
            first = providers.parse(json.loads((cache / f'invoices_test_{d["id"]}{suffix}.json').read_text(encoding='utf8'))['text'])
            was_right = score(apply_date_order(first, 'MDY'), gold)['all_correct']
            out = cache / 'reread' / f'invoices_test_{d["id"]}{suffix}.json'
            if not out.exists():
                text, *_ = providers.call(MODEL, damage(img, variant), reread_prompt(validate(first)))
                out.write_text(json.dumps({'text': text}, ensure_ascii=False), encoding='utf8')
            second = providers.parse(json.loads(out.read_text(encoding='utf8'))['text'])
            right = score(apply_date_order(second, 'MDY'), gold)['all_correct']
            passes = not set(c['check'] for c in validate(second)) & READING_CHECKS
            kind = ('kept' if right else 'broken') if was_right else \
                   ('fixed' if right else ('silenced' if passes else 'still_flagged'))
            counts[kind] = counts.get(kind, 0) + 1
            details.append({'variant': variant or 'clean', 'id': d['id'], 'result': kind,
                            'first_checks': d['flagged'], 'second_checks': [c['check'] for c in validate(second)]})
            print(variant or 'clean', d['id'], kind, flush=True)
    result = {'prompt_version': version, 'counts': counts, 'details': details}
    (ROOT / 'results' / f'reread_{MODEL}_invoices_test_p{version}.json').write_text(json.dumps(result, indent=1), encoding='utf8')
    print(json.dumps(counts))


if __name__ == '__main__':
    main()
