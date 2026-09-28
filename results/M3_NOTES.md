# M3: Vision LLM extraction (measured 2026-09-28)

Run: `python eval_extract.py MODEL SPLIT [LIMIT]` (outputs `extract_<model>_<split>.json`). Self-check: `python test_extract.py`.
Every call goes straight from the image to a vision model (approach B). Model answers are cached per prompt version, so reruns are free and a changed prompt never reuses old answers.

## 1. Model trial (10 CORD test receipts, prompt 903ae630, free tiers)
| Model | Receipts fully correct | Median seconds | Notes |
|---|---|---|---|
| Gemini 3.1 Flash Lite | 9 / 10 | 4.9 | chosen |
| Gemini 3.5 Flash Lite | 8 / 10 | 5.3 | read "60.000" as 60 |
| GLM-4.6V-Flash (Z.ai) | 8 / 10 | 50 | too slow for a live demo |
| Gemma 4 31B | 7 / 9 | 141 | too slow; one server error |
| Qwen3.8-27B (Groq) | 7 / 10 | 1.6 | fastest, least accurate |
| Gemini 3.8 Flash | – | – | Google returned "high demand" (503) on every call; free tier 20/day |

10 receipts is a small sample (one receipt = 10 points). Only the best model got the full run, by decision.

## 2. Gemini 3.1 Flash Lite on 200 receipts (CORD, prompt 903ae630)
| | Test (100) | Validation (100, unseen) |
|---|---|---|
| Receipts fully correct | 94% | 96% |
| Total | 96.9% | 99.0% |
| Subtotal / tax | 96.9% / 95.1% | 100% / 100% |
| Line amounts (F1) | 96.0% | 98.0% |
| Failed calls or invalid JSON | 0 | 0 |
| Median time | 4.8 s | 4.7 s |

The 10 "wrong" receipts, checked one by one against the images:
- **4 real errors of one kind: thousands separator.** "31.000" read as 31 (test 5, 32, 78; validation 89). Everything scales by 1/1000 together, so the arithmetic checks cannot see it.
- 3 other real errors: a tax line read as an item (test 58, flagged), a discount amount left empty (validation 21, flagged), an extra non-item line (validation 96).
- 2–3 label errors where the model is right: test 26 (label misses a price), validation 86 (label duplicates an add-on), test 12 (arguable, 100% discounted bag).

Known limit, not fixed: the thousands-separator misread. Receipts were not re-run with the newer prompt yet (daily free limit); planned next.

## 3. Gemini 3.1 Flash Lite on 74 invoices (katanaml, synthetic English, US dates, European number format)
First run (prompt 903ae630) found one real problem: **day and month swapped** on ambiguous US dates (05/11/2021 read as 5 November), 16 of 74 invoices. The arithmetic checks cannot catch it (both readings are valid dates).

Fix (designed and tried on 50 **train** invoices only, then measured once on test and validation):
1. The model also returns each date exactly as printed (`issue_date_text`).
2. New check `date_ambiguous`: a printed date whose first two numbers are both 12 or less goes to review.
3. `date_order` setting (MDY or DMY) per vendor or country: once confirmed, printed dates are re-read in that order.

Results with the fix (prompt 4e4da96c):
| | Train (50, used to try the fix) | Test (26) | Validation (48, unseen) |
|---|---|---|---|
| Issue date, model alone | 76% | 77% | 69% |
| **Issue date with the vendor's date order** | 100% | **100%** | **100%** |
| Wrong dates flagged as ambiguous | 12 / 12 | 6 / 6 | 15 / 15 |
| Correct invoices flagged anyway | 1 / 36 | 4 / 18 | 7 / 30 |
| Subtotal, tax, invoice no., buyer, currency | 100% | 100% | 100% |
| Total | 100% | 96.2% (label typo) | 100% |
| Line amounts (F1) | 98.4% | 99.7% | 99.3% |

Cost of the fix: until a vendor's date format is confirmed, invoices with ambiguous dates go to review (that is most of the "correct invoices flagged").

Label errors found in the invoice set (model right, label wrong), checked against the images:
- test 13: label total 1,579,929.37, image shows $157,929.37; label also misses item 6 (33,238.05).
- test 22: label seller is a tax ID.
- validation 10: label seller typo "Dunn-Campbel.".
- validation 6, 11, 47: label leaves a line amount empty that the image shows.

## Cost
All runs used free tiers. Median tokens per call: about 1,290 in / 235 out for a receipt (Gemini). At paid Gemini 3.1 Flash-Lite prices ($0.25 / $1.50 per 1M, read 2026-09-28) that would be about $0.0007 per receipt (arithmetic, not a measured bill).
