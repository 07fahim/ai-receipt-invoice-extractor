import json
import re
from decimal import Decimal
from pathlib import Path

import pyarrow.parquet as pq

from schema import Document, Item

PARQUET = Path(__file__).parent / 'data' / 'cord_v2_test.parquet'

ITEM_KEYS = (('nm', 'item_name'), ('cnt', 'item_qty'), ('unitprice', 'item_unit_price'), ('price', 'item_amount'))
TOTAL_KEYS = (('subtotal_price', 'subtotal'), ('tax_price', 'tax'), ('discount_price', 'discount'), ('total_price', 'total'))


def as_list(x):
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def load(path=PARQUET):
    for row in pq.read_table(path).to_pylist():
        gt = json.loads(row['ground_truth'])
        words = [w['text'] for line in gt['valid_line'] for w in line['words']]
        yield gt['meta']['image_id'], row['image']['bytes'], gt['gt_parse'], words


def parse_amount(s):
    # CORD-only: '12.5' would become 125; providers return numbers, not strings
    s = str(s)
    if '%' in s:
        return None
    neg = '-' in s
    s = re.sub(r'[^\d.,]', '', s).strip('.,')
    if not re.search(r'\d', s):
        return None
    last = max(s.rfind('.'), s.rfind(','))
    if last != -1 and len(s) - last - 1 == 2:  # "x.99": decimal part
        value = Decimal(re.sub(r'\D', '', s[:last]) + '.' + s[last + 1:])
    else:
        value = Decimal(re.sub(r'\D', '', s))
    return -value if neg else value


def first_amount(d, key):
    return next((a for a in (parse_amount(v) for v in as_list(d.get(key)) if isinstance(v, str)) if a is not None), None)


def to_document(gt_parse):
    items = []
    for m in as_list(gt_parse.get('menu')):
        name = next((v for v in as_list(m.get('nm')) if isinstance(v, str)), None)
        items.append(Item(description=name, quantity=first_amount(m, 'cnt'), unit_price=first_amount(m, 'unitprice'),
                          # itemsubtotal is after the line discount (schema amount is before); only used when price is missing
                          amount=first_amount(m, 'price') if 'price' in m else first_amount(m, 'itemsubtotal'),
                          discount=first_amount(m, 'discountprice')))
        # add-ons with their own price are separate lines; unpriced ones ("Less Ice") are notes
        items += [Item(description=next(iter(as_list(x.get('nm'))), None), amount=first_amount(x, 'price'))
                  for x in as_list(m.get('sub')) if isinstance(x, dict) and first_amount(x, 'price') is not None]
    sub = (as_list(gt_parse.get('sub_total')) or [{}])[0]
    tot = (as_list(gt_parse.get('total')) or [{}])[0]
    return Document(doc_type='receipt', items=items, subtotal=first_amount(sub, 'subtotal_price'),
                    tax=first_amount(sub, 'tax_price'), service_charge=first_amount(sub, 'service_price'),
                    discount=first_amount(sub, 'discount_price'), total=first_amount(tot, 'total_price') if 'total_price' in tot
                    else first_amount(tot, 'total_etc'))


def fields(gt_parse):
    out = []
    for item in as_list(gt_parse.get('menu')):
        if 'price' not in item and 'itemsubtotal' in item:
            item = {**item, 'price': item['itemsubtotal']}  # some receipts label the line amount this way
        for key, name in ITEM_KEYS:
            out += [(name, v) for v in as_list(item.get(key)) if isinstance(v, str)]
    for group in ('sub_total', 'total'):
        for g in as_list(gt_parse.get(group)):
            for key, name in TOTAL_KEYS:
                out += [(name, v) for v in as_list(g.get(key)) if isinstance(v, str)]
    return out
