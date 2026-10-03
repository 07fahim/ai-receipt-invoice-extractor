import json
import re
from decimal import Decimal
from pathlib import Path

from schema import Document, Item

DATA = Path(__file__).parent / 'data' / 'wildreceipt'  # download.openmmlab.com/mmocr/data/wildreceipt.tar (licence unclear: local only)
PRICE, SUBTOTAL, TAX, TOTAL = 15, 17, 19, 23  # class_list.txt
NUMBER = re.compile(r'-?[.,]?\d[\d.,]*\d|-?[.,]?\d')  # '.80' is 0.80
# Gulf and North African currencies have 3 decimals; on receipts with no 2-decimal amount, these words decide
# (label text has its spaces removed, 'CHILISMUSCAT', so places match inside words; short names like 'oman' would match 'woman')
THREE_DECIMALS = re.compile(r'\b(OMR|R\.O\b|BHD|KWD|KD|JOD|TND|IQD|LYD)\b|muscat|kuwait|bahrain|manama|tunisia|baghdad', re.I)


def number_in(text):
    found = NUMBER.findall(text.replace(' ', ''))
    return ([f for f in found if ',' in f or '.' in f] or found or [None])[-1]  # '13.99T1': the price, not the tax code


def decimal_point(amounts, words=()):
    # the separator before the last 2 digits of this receipt's amounts ('16.24' -> '.'), if there is exactly one
    points = {m[-3] for m in map(number_in, amounts) if m and re.search(r'\d[.,]\d\d$', m)}
    if len(points) == 1:
        return points.pop()
    return '.' if not points and any(THREE_DECIMALS.search(w) for w in words) else None


def amount(text, point=None):
    # '$13.99', '13.99T1', '1,234.50', and European '4,50' or '1.234,50' -> Decimal.
    # Many receipts are European: a comma before the last 1-2 digits is the decimal point.
    # 3 digits after the receipt's own decimal point are decimals ('2.619' per gallon next to '16.24'); otherwise thousands.
    number = number_in(text)
    if number is None:
        return None
    last = max(number.rfind('.'), number.rfind(','))
    decimals = len(number) - last - 1
    if last != -1 and (decimals <= 2 or number[last] == point):
        number = (re.sub(r'[.,]', '', number[:last]) or '0') + '.' + number[last + 1:last + 1 + (decimals if decimals <= 3 else 2)]  # '$0.99101': a code typed onto the price
    else:  # '13,990' or '50.000': thousands
        number = re.sub(r'[.,]', '', number)
    return Decimal(number)  # refunds printed '108.85-' or '($3.13)' stay positive, as the app stores them


def one(values):
    # a field labelled twice with different numbers (total before and after tip, say) can't be scored
    values = {v for v in values if v is not None}
    return values.pop() if len(values) == 1 else None


def to_document(annotations):
    money = [a['text'] for a in annotations if a['label'] in (PRICE, SUBTOTAL, TAX, TOTAL)]
    point = decimal_point(money, [a['text'] for a in annotations])
    by = lambda label: [amount(a['text'], point) for a in annotations if a['label'] == label]
    taxes = [v for v in by(TAX) if v is not None]  # two tax lines (CGST and SGST, say) may be equal; their sum is the tax, so only a single line is scored
    return Document(doc_type='receipt', subtotal=one(by(SUBTOTAL)), tax=taxes[0] if len(taxes) == 1 else None, total=one(by(TOTAL)),
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
    assert amount('13.99T') == Decimal('13.99') and amount('-2.00') == Decimal('-2.00') and amount('13.99T1') == Decimal('13.99')
    assert amount('4,50') == Decimal('4.50') and amount('1.234,50') == Decimal('1234.50') and amount('0,00') == 0
    assert amount('.80') == Decimal('0.80') and amount('$.99') == Decimal('0.99') and amount('-.50') == Decimal('-0.50')
    assert amount('50.000') == Decimal('50000') and amount('13,990') == Decimal('13990') and amount('12.5') == Decimal('12.5')
    assert amount('108.85-') == Decimal('108.85') and amount('($3.13)') == Decimal('3.13')
    assert amount('$2.619', '.') == Decimal('2.619') and amount('1,234', '.') == Decimal('1234') and amount('2.619', ',') == Decimal('2619')
    assert amount('$0.99101', '.') == Decimal('0.99') and amount('6.900', '.') == Decimal('6.900')
    assert decimal_point(['$16.24', '$2.619']) == '.' and decimal_point(['4,50', '1.234,50']) == ','
    assert decimal_point(['6.900', '19.729'], ['CHILISMUSCAT']) == '.' and decimal_point(['24,000', '69,000'], ['TOTAL']) is None
    assert one([Decimal('5'), Decimal('5'), None]) == Decimal('5') and one([Decimal('5'), Decimal('6')]) is None
    for split in ('test', 'train'):
        total = sum(1 for _ in (DATA / f'{split}.txt').open(encoding='utf-8'))
        kept = list(load(split))
        print(split, f'{len(kept)} of {total} receipts scorable;',
              'subtotal labelled on', sum(d.subtotal is not None for _, _, d in kept), '; tax on', sum(d.tax is not None for _, _, d in kept))
    print('ok')
