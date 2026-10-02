import json
from datetime import datetime
from pathlib import Path

import pyarrow.parquet as pq

from cord import parse_amount
from schema import Document, Item

DATA = Path(__file__).parent / 'data'


def to_document(g):
    # line amount = net (before VAT); subtotal = total net, tax = total VAT, total = gross
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
    for n, row in enumerate(pq.read_table(DATA / f'katanaml_{split}.parquet').to_pylist()):
        g = json.loads(row['ground_truth'])['gt_parse']
        h, s = g.get('header'), g.get('summary')
        if not (isinstance(h, dict) and isinstance(s, dict) and 'invoice_date' in h
                and all(k in s for k in ('total_net_worth', 'total_vat', 'total_gross_worth'))):
            continue
        yield n, row['image']['bytes'], to_document(g)


PHOTO_SETS = {
    'photos_indian': 'indian_invoices/Photos/Photos',  # Kaggle surajitsadhukhan/indian-grocery-tax-invoice-image-dataset, CC BY 4.0
    'photos_us': 'us_receipts',  # ExpressExpense sample receipt dataset (US restaurants), CC0
}


def load_photos(folder):
    for n, f in enumerate(sorted((DATA / folder).glob('*.jpg'))):
        yield n, f.read_bytes(), None
