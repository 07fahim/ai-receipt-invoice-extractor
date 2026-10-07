# M4: rate and tax number checks (measured 2026-10-07)

Status (2026-10-07): shipped with prompt b4907187; latest numbers in section 5.

The AI now also reads `tax_rate`, `tax_kind`, `discount_rate` and `seller_tax_id` (prompt 36d2b5dd). New checks:
`tax_rate`, `discount_rate`, `tax_id_invalid`; notes `tax_id_missing` and `older_than_upload` (a note never
changes the status). `eval_validation.py` catch counts now ignore notes (`validate.review` drops them), so a
planted mistake caught only by a note no longer counts as caught.

**Status (first round): stopped before the full re-runs.** One of the 6 expected catches failed live (Walmart) and one sample
got a new false alarm from the rate check (Arax). The prompt and the rules were not changed. CORD, invoice and
US receipt sets were not re-run with 36d2b5dd, so the README numbers still belong to be0376e0 (US receipts to 9edae16b).

## 1. Answer keys, no model calls (`python eval_rates.py`)
katanaml invoices (train, validation, test) whose lines all print the same VAT %: 472 answer keys (399 / 48 / 25),
all at 10%. None has a discount, so `discount_rate` is not tested here.

| | Result |
|---|---|
| Rate flags on correct answer keys | 0 / 472 |
| Tax raised by 1% (total kept consistent) | 456 / 463 caught |
| Tax raised by 5% | 469 / 469 |
| Tax raised by 10% | 469 / 469 |
| Tax lowered by 5% | 466 / 469 |

3 keys have no total and are skipped in the planted runs (train 134, 168, 185). The 10 misses are all inside the
allowed room, checked by hand: 7 in the +1% row (most under 1 cent per line, e.g. 0.75 to 0.76; 2 of those 7 became
a whole number, 21.00 and 6.00, which got the 0.5 room for whole-unit currencies), and 3 in the -5% row (0.15 to
0.30 per line, within 1 cent). (This table was measured with the tax_rate room at 0.5 for a whole-number tax;
current code uses room 1, see section 5 for the counts under today's rules.)

CORD and the synthetic Bangladeshi set were not run: CORD keys have no printed rate field, and the BD set was not
part of this run.

## 2. Live readings, Gemini 3.1 Flash-Lite, prompt 36d2b5dd (35 calls, no retries)
The 7 test documents (made with mistakes on purpose), Harbor Fresh (synthetic) and the 27 other private samples.
Every field below was compared with the image by eye.

| Document | Read (rate, kind, discount rate, tax no.) | Checks fired | Expected | Result |
|---|---|---|---|---|
| Maple Home | 8.5, sales_tax, 10, none | total_math, tax_rate | + sales tax above its rate | caught |
| GreenLeaf | 20, vat, 10, GB123 4567 89 | tax_rate, tax_id_invalid | VAT rate, invalid VAT no. | caught |
| Aarav | null (several rates), gst, null, 07AAHCA1234F1Z5 | none | passed | passed |
| Nandan | 15, vat, 5, none | items_sum, tax_rate, note no VAT no. | + VAT rate, note | caught |
| Mehedi | 15, vat, 5, none | tax_rate, note no VAT no. | VAT rate, note | caught |
| Walmart | **null**, sales_tax, null, none | line_math x7 | sales tax above its rate | **missed** |
| Target | 7, sales_tax, 10, none | discount_rate, line_math x4, date | + discount above its rate | caught |
| Harbor Fresh | 8.25, sales_tax, null, none | items_sum, date | (not in the table) | subtotal mistake caught |

Live catches: 5 of 6. Walmart prints "SALES TAX 0.00% $2.86"; the model returned `tax_rate: null`, so the rule
had nothing to check. The receipt still goes to review, but only because the model read the row numbers 1-8 as
quantities (line_math), a reading error. Target has the same row-number misreading.

The 27 older samples, against their be0376e0 answers re-checked with today's rules:

| Sample | Change | Real? |
|---|---|---|
| images (7).jpg (Arax) | new `tax_rate`: "VAT 5% of 1,110 is 55.50. The document says 59.95" | **No, false alarm.** The bill charges service 10% = 109 and VAT 5% = 59.95 on 1,090 + 109 = 1,199: the 20 taka water is left out of both. Items exempt from VAT are legal, and the VAT rule only allows for that on US sales tax |
| download.jpg (Star Hotel) | new `total_math` | **No, model reading.** The new answer adds a "Water" line with no amount (the photo has 6 names and 5 prices). That empty line stops the included-VAT rule from seeing the lines reach the total; without it the receipt passes. Money fields are right. Not caused by the new checks |
| Tax.png (Singer, Mushak-6.3) | new `tax_rate` | Already flagged (total_math): the invoice does not add up itself and takes its discount off the VAT column |
| handwritten.png | items_sum and line_math gone | Better: line 3 now read 240 (printed 240) |
| utility bill.png | items_sum and total_math gone | Total now the amount to be paid (9,983,196), as under a19decf8 |
| Mushak-6.3.png, images (8).jpg, electric bill.png, images (4).jpg | note: no VAT number | Right: none printed (images (8) prints "BIN:" with nothing after it) |
| utility bill.png | note: no VAT number | Wrong: "VAT ID NO." is printed sideways in the right margin. Note only |
| images (7).jpg | seller_tax_id "Applied" | Copied as printed ("BIN: Applied"), so no note |

Tax numbers checked against the image: Star Hotel (000107602-0201) and Singer (000038787-0204) match. The tax
numbers read on Shwapno, Arong, images (1), (2), (9) and (11) were not checked by eye. Among the 7 test documents
and Harbor Fresh, tax_rate is right on every one except Walmart (0.00%).

## 3. Not measured yet
Re-runs with 36d2b5dd of CORD test (100), invoices test (26) and validation (48), US receipts first 30, and the
rate-reading accuracy on invoices (`python eval_rates.py 36d2b5dd`). Waiting on a decision about the Walmart
reading and the Arax false alarm.

Bangladeshi bills where tax holds VAT plus supplementary duty and only the VAT % is printed can flag tax_rate
(probe only, not measured on real bills).

## 4. Prompt 9db1851c (2026-10-07): printed 0% copied as 0, VAT-included total by the printed rate
Two changes: the prompt says `0 if "0%" or "0.00%" is printed` for tax_rate; `total_math` also accepts VAT included
when the printed rate gives exactly the tax (tax within 0.01 of total x rate / (100 + rate)), with no line total
needed. The Arax VAT rule (water left out of VAT) is unchanged on purpose.

### Live samples (35 calls, Gemini 3.1 Flash-Lite, no retries), against 36d2b5dd with today's rules
Expected catches: 6 of 6. Walmart now reads tax_rate 0 and gets `tax_rate` ("Tax 0% of 29.18 is at most 0.00");
its row numbers are no longer read as quantities, so line_math is gone. Maple, GreenLeaf (rate + invalid VAT no.),
Nandan, Mehedi and Target unchanged. Star Hotel passes (the "Water" line with no amount is still there).

Other changes, each checked on the image:

| Sample | Change | Real? |
|---|---|---|
| handwritten.png | new items_sum + line_math; date 20/05 read as 20/06 | Misreads: line 3 280 (printed 240, caught); the date is not caught |
| memo.png | items_sum + line_math gone | Better: line 3 now 240 as printed |
| utility bill.png | new total_math | Total now the "Bill month total" 9,983,196.70 (was the 9,983,196.00 to be paid); the service charge 10 is read again on top of the principal, which already holds it. The cents remove the rounding room that hid this |
| costco-receipt.png | tax_rate 0 | No % printed (only "Tax $0.00"); harmless, no check runs |
| images (3).jpg | seller_tax_id 143775668 | Right: the Greek "ΑΦΜ" number |
| images (8).jpg | "Auto Round -0.25" no longer a discount; currency BDT | Total still passes; BDT right (Dhaka) |
| images (4), (6) | doc_number / vendor dropped | Old values were a payment number and a table number; no check uses them |

### Datasets (same prompt, no retries, under 12 calls a minute)
Baselines from results/M3_NOTES.md: be0376e0 for CORD and invoices, 9edae16b for US receipts. Three prompt changes
lie in between (a19decf8, 36d2b5dd, 9db1851c), so a change cannot be pinned on one of them. "Unflagged" = wrong and
no check fired except the day/month question. Old answers were re-checked with today's rules: same counts as stored.

| Set | Fully correct | Total correct | Wrong and unflagged | Correct but flagged |
|---|---|---|---|---|
| CORD test (100) | 91 → 87 | 90 → 88 of 96 | 2 → 1 | 5 → 5 |
| Invoices test (26) | 20 → 19 | 25 → 25 | 6 → 7 | 6 → 5 |
| Invoices validation (48) | 31 → 32 | 48 → 48 | 17 → 16 | 8 → 9 |
| US receipts, first 30 (no answer key) | passed 20 → 21 | | | |

Most invoice "unflagged" errors are day/month dates, which the vendor's date order fixes. Without them: test 2 → 2
(13, 22), validation 4 → 5 (new: 48, buyer "Hopkins-Moreono", printed "Hopkins-Moreno"; no check reads names).

CORD changes, images opened:
- 33, 94 (were right) and 14 (already wrong): the service charge is added into the tax (33: 11,070 + 19,557 =
  30,627). All flagged by total_math.
- 41: the 5% service charge is also copied as tax (none printed). Scored correct (the key has no tax), flagged.
- 34, 63 (were right): "93.500" and "57.000" read as 93.5 and 57. Flagged by total_format. Not opened (total_text and
  the key agree on what is printed).
- 58: now right; the "PB1" tax line is no longer listed as an item. 39: items_total gone, the line discounts now
  give 3,112,800 as printed (the key has no total).
- 90: **new false alarm**. Prints "Pb1 2,681" with no rate; the model filled in 10%. 10% of 26,818 is 2,681.80,
  the receipt drops the 0.80, over the 0.5 room.

US receipts: 15 **new false alarm** (total_math). The model now lists the unpriced side dishes ("Mac n Cheese",
"French Fries") as lines with no amount, so the rule cannot see that the -6.00 discount is already inside the
lines; without those two lines the receipt passes. 11: line_math gone, the weighed beef ribs now read 1 x 36.86
(money right; the quantity suggestion no longer fires). 18 and 24 read their printed rates (8.25%, 9%) and lose the
check number; 25 gains "Order 97". No other change.

Rate reading on invoices (`python eval_rates.py 9db1851c`): 53 right, 20 wrong of 73. All 20 are null where the
summary prints one rate (10%), e.g. test 10 (opened). Missed reads only: the rate check is skipped, no false alarm.
Answer keys and planted taxes unchanged from section 1 (0 / 472 false; 456/463, 469/469, 469/469, 466/469).

CORD validation was not run: the plan was to stop and report if CORD test dropped.

## 5. Prompt b4907187 (2026-10-07): rate copied only when printed; tax never holds the service charge
Same rules as section 4, plus: whole-number tax room 1 (a truncated 2,681 for 2,681.80), the tax rate base no longer
takes off a discount the subtotal already holds, and the missing tax number note only for BDT, INR, GBP and EUR.
Gemini 3.1 Flash-Lite, under 12 calls a minute; 503 "high demand" retries on CORD, 1 invoice read failed after retries.

### Live samples (35)
6/6 expected catches (Maple, GreenLeaf rate and VAT number, Nandan, Mehedi, Target discount, Walmart 0% tax).
Star Hotel passes. Changes against 9db1851c, images opened: handwritten memo now fully correct (240 and 20/05/2024 as
printed; was 280 and 20/06), utility bill loses its total_math false alarm. Arax still flagged (water left out of VAT
and service charge; kept by decision).

### Datasets (baseline be0376e0 for CORD and invoices, 9edae16b for US)
| Set | Fully correct | Total correct | Wrong and unflagged | Correct but flagged |
|---|---|---|---|---|
| CORD test (100) | 91 / 87 / **90** | 90 / 88 / **88** of 96 | 2 / 1 / **1** | 5 / 5 / **4** |
| Invoices test (26) | 20 / 19 / **18** | 25 / 25 / **25** | 2 / 2 / **2** | 6 / 5 / **4** |
| Invoices validation | 31/48 / 32/48 / **32/47** | 48 / 48 / **47 of 47** | 3 / 3 / **3** | 8 / 9 / **9** |
| US receipts, first 30 | passed 20 / 21 / **21** | | | |
(baseline / 9db1851c / b4907187; unflagged = wrong minus wrong_docs_flagged_by_validation in each results file summary. Section 4 counted the invoice sets another way; compare within this table only.)

CORD changes against the baseline, images opened:
- 0 and 79 (were right): every amount printed as "60.000" / "22.000" with no other separator; read as 60 and 22.
  Same answer on 3 reads each (repeat2, repeat3), so it is this prompt, not chance. Both flagged (total_format);
  79 also gets the "1,000 times too small" fix, 0 does not (its tax 5.455 keeps the math off).
- 58: now right. 34 and 63 (wrong under 9db1851c) right again.
- 33: tax_rate fires. The shop charged PB1 10% on the amount before the 67,000 item discount
  (10% of 184,500 + 11,070 = 19,557); message now "VAT 10% of 117,500 is 11,750. The document says 19,557."
Invoices test 3 and 8: day and month swapped, both flagged date_ambiguous. US 11 (Smoke City): the weighed brisket now
reads 1 x 36.86 (money right, the 1.89 lb weight lost, no flag); the quantity suggestion no longer fires there.
US 15 false alarm from section 4 is gone.

New checks on the datasets after the fixes: CORD tax_rate 1 (33), no other rate, discount or tax number flag and no
missing tax number note (was 33 of 100 CORD receipts before the currency rule). Invoices and US: none.

Rate reading (`python eval_rates.py b4907187`): 72 right, 0 wrong (9db1851c: 53 / 20). Answer keys: 0 / 472 false
flags; planted tax caught +1% 455/463, +5% 468/469, +10% 469/469, -5% 465/469 (room 1 for whole-number tax costs
one catch in three of the four rows).

Ship rule: not met as written. Fully correct drops 1 on CORD and 2 on invoices test; CORD totals drop 2 (0 and 79).
Every new error is flagged and no money error is silent. Decision (user, 2026-10-07): keep b4907187, no more prompt
rounds on the free quota (each round of ~240 calls moved 2-4 borderline documents in both directions).

## Known limits
- Tax rate and seller tax number are read but cannot be edited on the review page yet, so a misread rate or tax
  number can only be cleared by saving the document as reviewed. Follow-up.
- Webhook payloads carry notes in `checks` too (with `level: "note"`); the n8n alert should skip them.

## 6. Weights and units (all 79 unit items in the b4907187 readings, images opened for the odd ones)
Read right or flagged: weight on the item line (13 of 13 weighed items in the samples), weights printed rounded
(Shwapno 1.03 kg at 41.36: inside the line check's half-step room), pack size in the name (5 kg rice x 1), part of a
kg at a per-kg price, dozens and pieces, quantity with no unit price (line check skipped), row numbers read as
quantities (flagged). A weight read as a whole number is flagged and the quantity fix is offered.
Gap: a weight on its own sub-line with the line quantity printed as 1 (Smoke City: "Weight: 1.89 lbs @ $19.50/lbs")
is read 1 x 36.86: money right, weight and per-pound price lost, not flagged. Not measured: grams sold at a per-kg
price ("500 g @ 650/kg"). Next task: about 8 made-up receipts for sub-line weights, grams per kg and fuel; one prompt
rule for "weight @ price per unit" sub-lines; test on those plus Smoke City (about 9 calls) before any dataset re-run.

### 6a. Sub-line weight rule (prompt fef31308, 2026-10-08)
One rule added: "If a sub-line prints a weight @ price per unit, use them as the quantity and unit price."
Tested on 8 made-up receipts (invented shops, rendered from HTML, answer key from the same script) and Smoke City:
9 calls. The made-up receipts were not read with b4907187, so Smoke City is the only before/after.

| Receipt | Case | Result |
|---|---|---|
| Smoke City (real, CC0) | weight sub-line, qty column 1 | 1.89 x 19.50 (was 1 x 36.86), no flag |
| Oak Pit BBQ | same layout | 2.14 x 18.75 right |
| Corner Deli | two weight sub-lines + "2 @ $1.25" | all right, bagels stay 2 x 1.25 |
| Hillside Butchers | kg sub-line, GBP | 0.742 x 9.80 right |
| Meghna Bazar | kg sub-line, BDT | 1.25 x 780 right |
| Padma Fish | grams at a per-kg price, item line | 0.5 x 1600, 0.25 x 1200 right |
| Green Basket | grams on item line and sub-line | 0.75 x 2.40, 0.4 x 0.90 right |
| Ridgeline Fuel | gallons sub-line | 12.345 x 3.899 right |
| Lindenhof Fuel | litres, comma decimals, VAT included | 32.5 x 1.479 right |

No money amount wrong. Two differences from the key were key mistakes, checked on the images: the coffee line prints
no quantity or unit price (read null, as the prompt asks), and the VAT-included fuel receipt prints no subtotal (read
null). Every made-up receipt got date_ambiguous: the made-up date 10/05/2026 really is ambiguous. Smoke City got no
flag. Next: the dataset re-measure before this prompt ships.

Dataset re-measure with fef31308 (204 calls, 0 errors, 2026-10-08), against b4907187, same scoring and today's rules:

| Set | Fully correct b4907187 -> fef31308 | Wrong and not flagged | Correct but flagged |
|---|---|---|---|
| CORD test | 90 -> 90 of 100 | 1 -> 1 (test 26) | 4 -> 4 |
| Invoices test | 18 -> 19 of 26 | no new ones | 3 and 19 now right, 25 now wrong (date order swaps, all flagged ambiguous) |
| Invoices validation | 32 of 47 -> 33 of 48 | same 15 | doc 24 (failed read before) now right, flagged ambiguous date |
| US receipts (passed) | 21 -> 21 of 30 | - | - |

eval_rates: 0 of 472 keys flagged, the same planted errors caught, rate read 73 right, 0 wrong (72 before).
Changes checked on the images: Smoke City now 1.89 x 19.50. CORD 63 and 79 swap the "19.000"/"22.000" thousands misread
(each flagged by total_format; net 0). CORD 43 "6 Pcs Cheese Tart" now 6 x (no unit price): either reading fits the
print, money unchanged. US 15 (Hammocks) drops the two price-less sides under Shrimp Entree, which removes a false
total_math flag. On many CORD lines the unit price now comes back as amount / quantity where none is printed (and on a
few the other way): the line check already passed on those, so no flag changes.
Ship rule (no new wrong-and-unflagged, no unexplained drop): passed.
