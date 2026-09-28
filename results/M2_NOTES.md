# M2: Validation checks on CORD-v2 (measured 2026-09-28)

Run: `python eval_validation.py` (test split, output `validation.json`) and `python eval_validation.py validation` (held-out split, output `validation_validation.json`). Self-checks: `python test_validate.py`, `python test_eval_ocr.py`.

The checks (`validate.py`) are plain code, no AI. A document that fails any check goes to human review.

| Check | Rule |
|---|---|
| total_present | a total was found |
| items_missing | amounts were found but no line items |
| items_sum | lines (after line discounts) add up to the subtotal, exactly; tax-inclusive lines may equal subtotal + tax |
| total_math | subtotal + tax + service charge − discount = total (the total may be cash-rounded by up to 0.05%) |
| items_total | when there is no subtotal: lines + tax + service − discount = total, with the same 0.05% allowance; tax may also be treated as already included |
| line_math | quantity × unit price = line amount |
| date_future, due_before_issue | issue date not in the future; due date not before issue date |
| currency_code | valid ISO 4217 code |

## Headline (held-out split, checks not changed after seeing it)
The checks were built and tuned on the CORD **test** split (100 receipts). They were then run once, unchanged, on the CORD **validation** split (100 other receipts). The held-out numbers are the honest ones.

| | Test split (used for tuning) | Validation split (held out) |
|---|---|---|
| Correct receipts flagged | 7 of 100 | 9 of 100 |
| Simulated mistakes caught, all 8 types | 93.0% (548 / 589) | 95.0% (537 / 565) |
| Weakest type: total misread by one digit | 66.7% (62 / 93) | 75.8% (69 / 91) |

The overall catch rate depends on the mix of mistake types (4 of the 8 are caught 100% of the time), so the per-type table below is the real result.

## Catch rate per simulated mistake
One mistake is injected at a time into receipts that pass, and we count how often the checks flag it.

| Injected mistake | Test | Held out |
|---|---|---|
| total read 1000× off (thousands vs decimal separator) | 100% (93) | 100% (91) |
| subtotal taken as total | 100% (41) | 100% (38) |
| cash paid taken as total | 100% (44) | 100% (37) |
| tax missed | 100% (39) | 100% (38) |
| line item dropped | 96.8% (93) | 100% (90) |
| line item duplicated | 96.8% (93) | 100% (90) |
| line amount misread (one digit) | 95.7% (93) | 93.3% (90) |
| total misread (one digit) | 66.7% (93) | 75.8% (91) |

Limits, found by looking at the missed cases:
- **Total misread by one digit:** all 31 misses on the test split are last-digit changes that stay inside the 0.05% cash-rounding allowance (largest: 17,500 read as 17,508).
- **Line amounts on receipts without a subtotal** are compared with the total, so they get the same 0.05% allowance. "Exact line sums" only holds when a subtotal exists.
- **Lines without a price** (headers like "=*LARGE*==", unpriced drinks) switch the line-sum checks off for that receipt. Counting them as 0 was tried: no gain and one more false alarm, so it was not kept.
- **Wrong tax on receipts without a subtotal is not caught:** items_total also accepts "tax already included". None of the simulated mistakes test a wrong tax value.
- A duplicated line that is 100% discounted adds nothing and cannot be caught.
- The mistakes are simulated. Real extraction mistakes are measured in M3.

## Correct receipts that still get flagged
Each one checked against its labels.

Test split (7):
- 4 have no total in the labels, only the cash paid (docs 9, 39, 57, 76). Flagging them is correct.
- Doc 0: the labels do not add up.
- Doc 12: a 100% discounted line.
- Doc 43: VAT included, subtotal = total.

Held-out split (9):
- VAT already included in prices (docs 2, 77).
- 1-rupiah rounding in the subtotal (doc 13: lines 41,363, subtotal 41,364).
- Total rounded to 500, beyond the 0.05% allowance (doc 95).
- Discount counted twice in the labels (doc 7).
- Duplicated add-on price in the labels (doc 86).
- Tax labelled as "etc" (doc 94).
- No total in the labels (docs 29, 49).

**Main real-world limitation: VAT-inclusive receipts** (tax printed, but already inside the total) get flagged when subtotal = total. That is the normal layout in the EU and UK. The planned fix is a `tax_included` field set by the extractor, tested on invoices in M3.

Ideas **not** adopted, because testing them now would use up the held-out split:
- allow rounding only when the total is a round number (all cash-rounded totals seen are multiples of 100)
- allow 1-unit rounding on line sums

They get tested on a new set (the CORD train split or invoices) before any change.

## How the test-split numbers got here
| Version | Correct receipts flagged | Catch rate |
|---|---|---|
| First version (0.1% tolerance everywhere, no line-vs-total check without subtotal) | 6 | 56.7% |
| + lines checked against total when no subtotal; loose tax-inclusive total rule removed | 7 | 84.6% |
| + exact line sums, rounding allowed on the total only | 7 | 88.3% |
| + flag documents with amounts but no line items | 7 | 93.0% |

Tolerance options measured before choosing (flagged correct receipts / catch rate, on the second version):
- none: 12 / 94.1%
- 0.01%: 8 / 89.9%
- 0.05%: 7 / 85.7%
- 0.1%: 7 / 84.6%

The number of test cases differs per option (555 to 589) because the set of receipts that pass changes. The 5 extra receipts flagged at zero tolerance were all cash-rounded totals (multiples of 100).
