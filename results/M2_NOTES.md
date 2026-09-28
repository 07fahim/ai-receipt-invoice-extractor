# M2: Validation checks on CORD-v2 test (measured 2026-09-28)

Run: `python eval_validation.py` (full output: `validation.json`). Self-checks: `python test_validate.py`, `python test_eval_ocr.py`.

The checks (`validate.py`) are plain code, no AI. A document that fails any check goes to human review.

| Check | Rule |
|---|---|
| total_present | a total was found |
| items_missing | amounts were found but no line items |
| items_sum | lines (after line discounts) add up to the subtotal, exactly; tax-inclusive lines may equal subtotal + tax |
| total_math | subtotal + tax + service charge − discount = total (the total may be cash-rounded by up to 0.05%) |
| items_total | when there is no subtotal: lines + tax + service − discount = total |
| line_math | quantity × unit price = line amount |
| date_future, due_before_issue | issue date not in the future; due date not before issue date |
| currency_code | valid ISO 4217 code |

## 1. Correct receipts that still get flagged: 7 of 100
Checked one by one against the ground-truth labels:
- 4 receipts (9, 39, 57, 76) have **no total in the labels**, only the cash paid. Flagging them is correct.
- Doc 0: the labels do not add up (discount equals the subtotal, total unchanged).
- Doc 12: a line with a 100% discount (the amount is 0 while qty × price is 880).
- Doc 43: tax printed but already included in the total (subtotal = total). Accepting this pattern would also accept "subtotal taken as total", a common mistake, so it is flagged on purpose.

So 3 of 100 are true false alarms: odd receipts that a human would want to look at anyway.

## 2. Catch rate on injected mistakes: 93.0% (548 of 589)
Take the 93 receipts that pass, inject one typical extraction mistake at a time, and count how often the checks flag it.

| Injected mistake | Caught | n |
|---|---|---|
| total read 1000× off (thousands vs decimal separator) | 100% | 93 |
| subtotal taken as total | 100% | 41 |
| cash paid taken as total | 100% | 44 |
| tax missed | 100% | 39 |
| line item dropped | 96.8% | 93 |
| line item duplicated | 96.8% | 93 |
| line amount misread (one digit) | 95.7% | 93 |
| total misread (one digit) | 66.7% | 93 |

Limits, found by looking at the missed cases:
- **Total misread by one digit** is the weakest: a change in the last digits (91,000 read as 91,070) stays inside the 0.05% cash-rounding allowance, and on one-item receipts where subtotal = total there is nothing else to compare against.
- **Lines without a price** (section headers like "=*LARGE*==", unpriced drinks) switch the line-sum checks off for that receipt (docs 26, 70). Counting them as 0 was tried and measured: no gain, one more false alarm, so it was not kept.
- A duplicated line that is 100% discounted adds nothing and cannot be caught (doc 31).

## How the numbers got here (all measured)
| Version | Correct receipts flagged | Catch rate |
|---|---|---|
| First version (0.1% tolerance everywhere, no line-vs-total check without subtotal) | 6 | 56.7% |
| + lines checked against total when no subtotal; loose tax-inclusive total rule removed | 7 | 84.6% |
| + exact line sums, rounding allowed on the total only | 7 | 88.3% |
| + flag documents with amounts but no line items | 7 | 93.0% |

Tolerance options measured before choosing (flagged correct receipts / catch rate): none 12 / 94.1%, 0.01% 8 / 89.9%, 0.05% 7 / 85.7%, 0.1% 7 / 84.6% (all on the second version). The 5 extra receipts flagged at zero tolerance were all cash-rounded totals, which is why only the total gets an allowance.

Caveat: the injected mistakes are simulated. Real extraction mistakes are measured in M3.
