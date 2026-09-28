"""Load the katanaml invoice set (HF katanaml-org/invoices-donut-data-v1, MIT tag; synthetic English invoices)."""
import json
from datetime import datetime
from pathlib import Path

import pyarrow.parquet as pq

from cord import parse_amount
from schema import Document, Item

DATA = Path(__file__).parent / 'data'


def to_document(g):
    """Ground truth as a schema Document. Seller and client strings include the address (name first).
    Line amount = net worth (before VAT); subtotal = total net, tax = total VAT, total = gross."""
    h, s = g['header'], g['summary']
    items = [Item(description=i.get('item_desc'), quantity=parse_amount(i.get('item_qty', '')),
                  unit_price=parse_amount(i.get('item_net_price', '')), amount=parse_amount(i.get('item_net_worth', '')))
             for i in g.get('items') or []]
    return Document(doc_type='invoice', vendor=h.get('seller'), buyer=h.get('client'), doc_number=h.get('invoice_no'),
                    issue_date=datetime.strptime(h['invoice_date'], '%m/%d/%Y').date(),
                    currency='USD' if '$' in s.get('total_gross_worth', '') else None,
                    subtotal=parse_amount(s['total_net_worth']), tax=parse_amount(s['total_vat']),
                    total=parse_amount(s['total_gross_worth']), items=items)


def load(split):
    """Yield (doc_id, image_bytes, gold Document). Rows whose labels are malformed are skipped (2 in validation)."""
    for n, row in enumerate(pq.read_table(DATA / f'katanaml_{split}.parquet').to_pylist()):
        g = json.loads(row['ground_truth'])['gt_parse']
        if not isinstance(g.get('header'), dict) or not isinstance(g.get('summary'), dict):
            continue
        yield n, row['image']['bytes'], to_document(g)
