import json
import re
import statistics
import time
from collections import Counter, defaultdict
from importlib.metadata import version
from pathlib import Path

import cord

ROOT = Path(__file__).parent
CACHE = ROOT / 'data' / 'ocr_cache'
OUT = ROOT / 'results' / 'ocr_baseline.json'
TEXT_FIELDS = {'item_name'}
CHANCE_OFFSETS = range(1, 6)  # score each doc's truth against 5 other docs' OCR


def digits(s):
    return re.sub(r'\D', '', s)


def squash(s):
    return ''.join(s.casefold().split())


def norm(s):
    return ' '.join(s.casefold().split())


def score_doc(pairs, ocr_lines):
    pool = Counter(digits(t) for line in ocr_lines for t in line.split())
    pool.pop('', None)
    seen = set(pool)
    text = squash(' '.join(ocr_lines))
    out = []
    for field, value in pairs:
        if field in TEXT_FIELDS:
            out.append((field, value, squash(value) in text))
            continue
        d = digits(value)
        if not d:
            continue
        if field.startswith('item_'):
            ok = pool[d] > 0
            pool[d] -= ok
        else:
            ok = d in seen
        out.append((field, value, ok))
    return out


def word_recall(gt_words, ocr_lines):
    gt = Counter(norm(w) for w in gt_words if w.strip())
    ocr = Counter(norm(t) for line in ocr_lines for t in line.split())
    return sum((gt & ocr).values()) / max(sum(gt.values()), 1)


def run_ocr(engine, doc_id, image):
    f = CACHE / f'{doc_id}.json'
    if f.exists():
        return json.loads(f.read_text(encoding='utf8'))
    t = time.perf_counter()
    o = engine(image)
    res = {'rapidocr': version('rapidocr'), 'seconds': time.perf_counter() - t, 'txts': list(o.txts or []),
           'scores': [float(s) for s in (o.scores or [])],
           'boxes': [b.tolist() for b in (o.boxes if o.boxes is not None else [])]}
    f.write_text(json.dumps(res, ensure_ascii=False), encoding='utf8')
    return res


def rates(hits):
    return {f: {'rate': round(sum(v) / len(v), 4), 'n': len(v)} for f, v in sorted(hits.items())}


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    OUT.parent.mkdir(exist_ok=True)
    docs_in = list(cord.load())
    engine = None
    if any(not (CACHE / f'{d[0]}.json').exists() for d in docs_in):
        from rapidocr import RapidOCR
        engine = RapidOCR()
        engine(docs_in[0][1])  # warm-up so model loading is not counted in latency

    ocrs = {doc_id: run_ocr(engine, doc_id, image) for doc_id, image, _, _ in docs_in}
    ids = [d[0] for d in docs_in]
    hits, chance, recalls, secs, docs = defaultdict(list), defaultdict(list), [], [], []
    for i, (doc_id, _, gt_parse, gt_words) in enumerate(docs_in):
        pairs = cord.fields(gt_parse)
        ocr = ocrs[doc_id]
        scored = score_doc(pairs, ocr['txts'])
        for field, _, ok in scored:
            hits[field].append(ok)
        for k in CHANCE_OFFSETS:
            for field, _, ok in score_doc(pairs, ocrs[ids[(i + k) % len(ids)]]['txts']):
                chance[field].append(ok)
        r = word_recall(gt_words, ocr['txts'])
        recalls.append(r); secs.append(ocr['seconds'])
        docs.append({'id': doc_id, 'word_recall': round(r, 4), 'seconds': round(ocr['seconds'], 3),
                     'missed': [[f, v] for f, v, ok in scored if not ok]})

    summary = {
        'dataset': 'CORD-v2 test', 'docs': len(docs),
        'ocr': f"RapidOCR {version('rapidocr')} (default models, CPU)",
        'word_recall_mean': round(statistics.mean(recalls), 4),
        'field_found_rate': rates(hits),
        'chance_rate_other_docs': rates(chance),
        'docs_missing_total': sum(any(f == 'total' for f, _ in d['missed']) for d in docs),
        'seconds_per_doc': {'median': round(statistics.median(secs), 3), 'max': round(max(secs), 3)},
    }
    OUT.write_text(json.dumps({'summary': summary, 'docs': docs}, indent=1, ensure_ascii=False), encoding='utf8')
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()
