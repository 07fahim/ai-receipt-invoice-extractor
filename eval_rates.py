import json
import sys
from decimal import Decimal as D

import pyarrow.parquet as pq

from invoices import DATA, to_document
from providers import parse
from validate import review, validate

# katanaml invoices: every line prints its VAT %; one rate on all lines gives the document's tax_rate


def keys(split):
    for n, r in enumerate(pq.read_table(DATA / f'katanaml_{split}.parquet').to_pylist()):
        g = json.loads(r['ground_truth'])['gt_parse']
        items = g.get('items') or []
        rates = {str(i.get('item_vat', '')).strip(' %') for i in ([items] if isinstance(items, dict) else items)}
        try:
            doc = to_document(g)
        except Exception:
            continue  # incomplete answer keys are skipped, as in invoices.load
        if len(rates) == 1 and doc.tax is not None and doc.subtotal is not None and rates != {''}:
            yield f'{split}_{n}', doc.model_copy(update={'tax_rate': D(rates.pop()), 'tax_kind': 'vat'})


docs = [x for s in ('train', 'validation', 'test') for x in keys(s)]
false = [(k, i['message']) for k, d in docs for i in review(validate(d)) if i['check'] in ('tax_rate', 'discount_rate')]
print(f'{len(docs)} answer keys with one VAT rate: {len(false)} rate flags (each must be a real mistake in the key)')
for f in false:
    print('  ', *f)
for p in ('0.01', '0.05', '0.10', '-0.05'):
    tried = caught = 0
    for k, d in docs:
        wrong = (d.tax * (1 + D(p))).quantize(D('0.01'))
        if wrong == d.tax or d.total is None:  # a key without a total cannot stay consistent
            continue
        tried += 1
        planted = d.model_copy(update={'tax': wrong, 'total': d.total + wrong - d.tax})  # the total stays consistent
        caught += any(i['check'] == 'tax_rate' for i in validate(planted))
    print(f'tax off by {p}: {caught}/{tried} caught')
if len(sys.argv) > 1:  # rate reading accuracy from cached answers of a prompt version: python eval_rates.py <version>
    right = wrong = 0
    for k, d in docs:
        split, n = k.rsplit('_', 1)
        path = DATA / 'llm_cache' / 'gemini-3.1-flash-lite' / sys.argv[1] / f'invoices_{split}_{n}.json'
        if path.exists():
            got = parse(json.loads(path.read_text(encoding='utf-8'))['text']).tax_rate
            right, wrong = right + (got == d.tax_rate), wrong + (got != d.tax_rate)
    print(f'tax_rate read: {right} right, {wrong} wrong')
