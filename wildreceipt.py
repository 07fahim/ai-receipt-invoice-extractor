import json
import re
from decimal import Decimal
from pathlib import Path

from schema import Document, Item

DATA = Path(__file__).parent / 'data' / 'wildreceipt'  # download.openmmlab.com/mmocr/data/wildreceipt.tar (licence unclear: local only)
PRICE, SUBTOTAL, TAX, TOTAL = 15, 17, 19, 23  # class_list.txt
AMOUNT = re.compile(r'-?\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|-?\d+(?:\.\d{1,2})?')


def amount(text):
    # '$13.99', '13.99T', '1,234.50' -> Decimal; the labels keep the printed text with spaces removed
    found = AMOUNT.findall(text.replace(' ', ''))
    return Decimal(found[-1].replace(',', '')) if found else None


def one(values):
    # a field labelled twice with different numbers (total before and after tip, say) can't be scored
    values = {v for v in values if v is not None}
    return values.pop() if len(values) == 1 else None


def to_document(annotations):
    by = lambda label: [amount(a['text']) for a in annotations if a['label'] == label]
    return Document(doc_type='receipt', subtotal=one(by(SUBTOTAL)), tax=one(by(TAX)), total=one(by(TOTAL)),
                    items=[Item(amount=v) for v in by(PRICE) if v is not None])


def load(split):
    # Only receipts whose labels give a total and at least one item price: without them a receipt can't be scored.
    for n, line in enumerate((DATA / f'{split}.txt').read_text(encoding='utf-8').splitlines()):
        r = json.loads(line)
        doc = to_document(r['annotations'])
        if doc.total is not None and doc.items:
            yield n, (DATA / r['file_name']).read_bytes(), doc


if __name__ == '__main__':
    assert amount('$13.99') == Decimal('13.99') and amount('1,234.50') == Decimal('1234.50') and amount('TOTAL') is None
    assert amount('13.99T') == Decimal('13.99') and amount('-2.00') == Decimal('-2.00')
    assert one([Decimal('5'), Decimal('5'), None]) == Decimal('5') and one([Decimal('5'), Decimal('6')]) is None
    for split in ('test', 'train'):
        total = sum(1 for _ in (DATA / f'{split}.txt').open(encoding='utf-8'))
        kept = list(load(split))
        print(split, f'{len(kept)} of {total} receipts scorable;',
              'subtotal labelled on', sum(d.subtotal is not None for _, _, d in kept), '; tax on', sum(d.tax is not None for _, _, d in kept))
    print('ok')
