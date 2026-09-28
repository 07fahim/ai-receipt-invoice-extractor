# M1: RapidOCR baseline on CORD-v2 test (measured 2026-09-28)

Setup: `pip install -r requirements.txt`, then download `data/test-00000-of-00001-9c204eb3f4e11791.parquet` from https://huggingface.co/datasets/naver-clova-ix/cord-v2 to `data/cord_v2_test.parquet`.
Run: `python eval_ocr.py` (RapidOCR 3.9.2, default models, CPU; the GTX 1050 is not used). Full per-doc output: `ocr_baseline.json`. Self-check: `python test_eval_ocr.py`.

"Found" = the ground-truth value can be read in the OCR text. This is the **ceiling for approach A** (OCR text + LLM), not extraction accuracy.
- Numbers: an OCR token with the same digits (60.000, 60,000 and Rp60.000 all match). Line-item numbers use each OCR token once; totals only need to appear somewhere.
- Item names: found inside the OCR text, ignoring case and spaces.
- "Chance" = the same rule applied against 5 *other* receipts' OCR. It shows how much of a rate could be luck.

| Field | Found | Chance | n |
|---|---|---|---|
| total | 93.7% | 1.7% | 95 |
| subtotal | 95.5% | 0.6% | 66 |
| tax | 88.1% | 0.5% | 42 |
| discount | 100% | 6.7% | 6 |
| item amount | 90.7% | 2.7% | 248 |
| item unit price | 89.6% | 4.5% | 67 |
| item name | 87.3% | 0.4% | 251 |
| item quantity | 70.9% | **35.0%** | 220 |

- Item quantity is mostly "1" or "2", so its number is weak evidence (35% by chance). It is judged properly in M3 when real extractions are scored.
- Word recall: 81.2% of the words CORD labels (item and total lines only) were read exactly. Precision is not reported: CORD does not label store name, address or footer, so it would be meaningless.
- Speed: median 1.63 s per receipt, max 6.7 s (first, uncached run).
- Not scored: sub-items (36 lines), service charge (12 receipts), cash/change/card amounts. Two tax values are "-" and are skipped.

What the misses are (checked by looking at the images and OCR output, not assumed):
- 6 of 95 receipts: the total was never read (docs 13, 14, 20, 30, 35, 93).
- Doc 13: the number column is clearly readable, but RapidOCR detected no numbers at all.
- Doc 20: dot-matrix digits read in pieces ("377" instead of "377,859").
- Doc 12: quantity glued to the price ("18120,000" for qty 1 + 120,000).
- Doc 85: "28 500" read with a space, so the rule misses a readable value (the rule is strict).
- Item names: letter errors ("AVOCADD COFFEE", "IOSMINE MT").

Notes for later milestones:
- M2: 12 receipts have a service charge, so "subtotal + tax − discount = total" fails on them even when the extraction is right. Validation must allow for service charge.
- M3: compare approach B (image straight to a vision LLM) on the receipts where OCR missed the total; cash and change amounts are likely to be confused with the total.
