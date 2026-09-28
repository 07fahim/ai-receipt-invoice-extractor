"""M2: how well the validation checks work on real receipts (CORD-v2 test ground truth).

1. False alarms: correct (ground-truth) receipts that get flagged anyway.
2. Catch rate: take receipts that pass, inject one typical extraction mistake, count how many get flagged.
Writes results/validation.json.
"""
import json
import random
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import cord
from validate import validate

OUT = Path(__file__).parent / 'results' / 'validation.json'


def bump_digit(value, rng):
    """Change one digit of an amount, like an OCR/LLM misread (5 -> 6)."""
    s = str(abs(value))
    pos = rng.choice([i for i, c in enumerate(s) if c.isdigit()])
    new = s[:pos] + str((int(s[pos]) + rng.randint(1, 9)) % 10) + s[pos + 1:]
    return Decimal(new) * (1 if value >= 0 else -1)


def mutations(doc, gt_parse, rng):
    """Yield (name, broken_doc). Each mutation is one realistic mistake; skipped when it can't apply."""
    d = doc.model_copy(deep=True)
    if doc.total:
        yield 'total_digit_misread', d.model_copy(update={'total': bump_digit(doc.total, rng)})
        yield 'total_off_by_1000x', d.model_copy(update={'total': doc.total / 1000})
    cash = cord.first_amount((cord.as_list(gt_parse.get('total')) or [{}])[0], 'cashprice')
    if cash and doc.total and cash != doc.total:
        yield 'cash_paid_taken_as_total', d.model_copy(update={'total': cash})
    if doc.subtotal and doc.total and doc.subtotal != doc.total:
        yield 'subtotal_taken_as_total', d.model_copy(update={'total': doc.subtotal})
    priced = [n for n, i in enumerate(doc.items) if i.amount]
    if priced:
        n = rng.choice(priced)
        yield 'line_item_dropped', d.model_copy(update={'items': [i for k, i in enumerate(d.items) if k != n]})
        yield 'line_item_duplicated', d.model_copy(update={'items': d.items + [d.items[n]]})
        items = [i.model_copy() for i in d.items]
        items[n] = items[n].model_copy(update={'amount': bump_digit(items[n].amount, rng)})
        yield 'line_amount_misread', d.model_copy(update={'items': items})
    if doc.tax:
        yield 'tax_missed', d.model_copy(update={'tax': None})


def main():
    rng = random.Random(0)
    docs = [(i, p, cord.to_document(p)) for i, _, p, _ in cord.load()]
    false_alarms = {i: [x['message'] for x in validate(doc)] for i, _, doc in docs}
    false_alarms = {i: m for i, m in false_alarms.items() if m}

    caught, examples = defaultdict(list), defaultdict(list)
    for i, p, doc in docs:
        if i in false_alarms:
            continue
        for name, broken in mutations(doc, p, rng):
            flagged = bool(validate(broken))
            caught[name].append(flagged)
            if not flagged and len(examples[name]) < 3:
                examples[name].append(i)

    total = [x for v in caught.values() for x in v]
    summary = {
        'dataset': 'CORD-v2 test ground truth', 'docs': len(docs),
        'flagged_ground_truth': len(false_alarms),
        'catch_rate_overall': {'rate': round(sum(total) / len(total), 4), 'n': len(total)},
        'catch_rate': {k: {'rate': round(sum(v) / len(v), 4), 'n': len(v)} for k, v in sorted(caught.items())},
    }
    OUT.write_text(json.dumps({'summary': summary, 'flagged_ground_truth': false_alarms,
                               'missed_examples': examples}, indent=1, ensure_ascii=False), encoding='utf8')
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()
