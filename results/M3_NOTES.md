# M3: Vision LLM extraction (measured 2026-09-28)

Run: `python eval_extract.py MODEL SPLIT [LIMIT] [PROMPT_VERSION]`. Self-check: `python test_extract.py`.
Every call sends the image straight to a vision model (approach B in the PRD). Answers are cached per model and prompt version; passing PROMPT_VERSION re-scores cached answers without calling the API.
Each table names the prompt version and results file it comes from (`results/extract_<model>_<split>[_first<N>]_p<version>.json`).

**Approach A (local OCR text + LLM) was not built.** M1 showed the local OCR never reads the total on 6 of 95 receipts, which caps approach A, while approach B read totals on 97–99% of receipts. The user decided to run only the best model. The PRD's M3 criterion is updated to match.

## 1. Model trial: 10 CORD test receipts, prompt 903ae630 (`*_test_first10_p903ae630.json`)
| Model | Fully correct | Median seconds | Notes |
|---|---|---|---|
| Gemini 3.1 Flash Lite | 9 / 10 | 4.9 | chosen |
| Gemini 3.5 Flash Lite | 8 / 10 | 5.3 | read "60.000" as 60 |
| GLM-4.6V-Flash (Z.ai) | 8 / 10 | 50 | slow |
| Gemma 4 31B | 7 / 9 | 141 | slow; 1 call failed (server error) |
| Qwen3.8-27B (Groq) | 7 / 10 | 1.6 | fastest, least accurate |
| Gemini 3.8 Flash | – | – | "high demand" (503) on every call |

- 10 receipts is a small sample: one receipt moves a score by 10 points.
- Timing includes any retry waits: the code waits 30/60/90 s on rate limits and server errors, and attempts were not recorded for these runs. The GLM and Gemma times may partly be waiting. They were not re-measured.

## 2. Gemini 3.1 Flash Lite on 200 CORD receipts, prompt 903ae630 (`*_test_p903ae630.json`, `*_validation_p903ae630.json`)
| | Test (100) | Validation (100, unseen) |
|---|---|---|
| Receipts fully correct (all money fields + line amounts; item names not included) | 94% | 96% |
| Total | 96.9% | 99.0% |
| Subtotal / tax | 96.9% / 95.1% | 100% / 100% |
| Line amounts (F1) | 96.0% | 98.0% |
| Wrong receipts flagged by the checks | 1 / 6 | 1 / 4 |
| Correct receipts flagged anyway | 5 / 94 | 6 / 96 |
| Failed calls or invalid JSON | 0 | 0 |
| Median time | 4.8 s | 4.7 s |

What the 10 "wrong" receipts are (each checked against its image):
- **4 real errors of one kind: thousands separator.** "31.000" was read as 31 (test 5, 32, 78; validation 89). Every amount scales by 1/1000 together, so the arithmetic checks cannot see it. This is why the checks caught so few of the wrong receipts.
- **3 other real errors:**
  - test 58: a tax line was read as an item (flagged)
  - validation 21: a discount amount was left empty (flagged)
  - validation 96: an extra non-item line
- **2–3 label errors where the model is right:**
  - test 26: the label misses a price
  - validation 86: the label duplicates an add-on
  - test 12: arguable (a 100% discounted bag)

Known limit, not fixed: the thousands-separator misread.

Receipts were **not yet re-run with the current prompt (4e4da96c)**; the daily free limit was reached. Until they are, these numbers belong to prompt 903ae630.

## 3. Gemini 3.1 Flash Lite on 74 invoices (katanaml: synthetic English invoices, US dates, European number format)

**First run, prompt 903ae630** (`*_invoices_*_p903ae630.json`):
- fully correct: 76.9% test, 66.7% validation
- the one real problem: **day and month swapped** on 17 of 74 invoices (test 4, validation 13), e.g. 05/11/2021 read as 5 November
- the arithmetic checks cannot catch this: both readings are valid dates

This first run looked at both test and validation. So **neither invoice split is unseen** for the date fix.

**The fix**, designed and tried on 50 **train** invoices, then run once on test and validation:
1. The model also returns each date exactly as printed (`issue_date_text`).
2. **New check `date_ambiguous`:** a printed date whose first two numbers are both 12 or less goes to review.
3. **`date_order` setting** (MDY or DMY) per vendor or country. Once confirmed, printed dates are re-read in that order.

**Results with the fix, prompt 4e4da96c** (`*_invoices_train_first50_p4e4da96c.json`, `*_invoices_test_p4e4da96c.json`, `*_invoices_validation_p4e4da96c.json`):
| | Train (50) | Test (26) | Validation (48) |
|---|---|---|---|
| Invoices fully correct, model alone | 72% | 69.2% | 62.5% |
| Issue date, model alone | 76% | 76.9% | 68.8% |
| Issue date with the vendor's date order | 100% | 100% | 100% |
| Wrong dates flagged as ambiguous | 12 / 12 | 6 / 6 | 15 / 15 |
| Wrong invoices flagged by the checks | 13 / 14 | 6 / 8 | 15 / 18 |
| Correct invoices flagged anyway | 1 / 36 | 4 / 18 | 7 / 30 |
| Subtotal, tax, invoice no., buyer, currency | 100% | 100% | 100% |
| Total | 100% | 96.2% (label typo) | 100% |
| Line amounts (F1) | 98.4% | 99.7% | 99.3% |

**Read these date numbers carefully:**
- **"Wrong dates flagged 100%" is true by design.** A day/month swap can only give a different valid date when both numbers are 12 or less, which is exactly what the check looks for.
- **"100% with the vendor's date order" assumes the correct order is known.** Here it is MDY for the whole dataset. In the app, the user confirms it once per vendor.
- **The new prompt made the model-alone dates worse:** 21 swaps instead of 17. Fully correct went from 76.9 / 66.7% to 69.2 / 62.5%. The fix works because of the printed text and the check, not because the model reads dates better.
- **Cost of the fix:** until a vendor's date format is confirmed, invoices with ambiguous dates go to review. That is why more correct invoices are flagged.

Label errors in the invoice set (model right, label wrong), checked against the images:
- test 13: the label total is 1,579,929.37 but the image shows $157,929.37; the label also misses item 6 (33,238.05)
- test 22: the label seller is a tax ID
- validation 10: the label seller has a typo, "Dunn-Campbel."
- validation 6, 11, 47: the label leaves a line amount empty that the image shows

## Cost
All runs used free tiers. Median tokens per call (Gemini 3.1 Flash Lite):
- receipts: about 1,290 in / 235 out
- invoices: about 1,325 in / 480–540 out

At paid Gemini 3.1 Flash-Lite prices ($0.25 / $1.50 per 1M tokens, read 2026-09-28), that is about $0.0007 per receipt and $0.001 per invoice. This is arithmetic from token counts, not a measured bill.
