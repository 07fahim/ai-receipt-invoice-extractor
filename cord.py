"""Load the CORD-v2 test split (parquet from Hugging Face naver-clova-ix/cord-v2, CC-BY-4.0)."""
import json
from pathlib import Path

import pyarrow.parquet as pq

PARQUET = Path(__file__).parent / 'data' / 'cord_v2_test.parquet'

ITEM_KEYS = (('nm', 'item_name'), ('cnt', 'item_qty'), ('unitprice', 'item_unit_price'), ('price', 'item_amount'))
TOTAL_KEYS = (('subtotal_price', 'subtotal'), ('tax_price', 'tax'), ('discount_price', 'discount'), ('total_price', 'total'))


def as_list(x):
    """CORD stores one value as a scalar/dict and several as a list."""
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def load(path=PARQUET):
    """Yield (doc_id, image_bytes, gt_parse, gt_words) for each document."""
    for row in pq.read_table(path).to_pylist():
        gt = json.loads(row['ground_truth'])
        words = [w['text'] for line in gt['valid_line'] for w in line['words']]
        yield gt['meta']['image_id'], row['image']['bytes'], gt['gt_parse'], words


def fields(gt_parse):
    """Flatten the gt_parse into (field, value) pairs that match the PRD schema.
    Not included: sub-items (menu[].sub, 36 lines in the test split; M3 decides how to score them),
    service charge, cash/change/card amounts and counts (not in the PRD schema)."""
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
