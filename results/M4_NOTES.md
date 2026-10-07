# M4: rate and tax number checks (measured 2026-10-07)

The AI now also reads `tax_rate`, `tax_kind`, `discount_rate` and `seller_tax_id` (prompt 36d2b5dd). New checks:
`tax_rate`, `discount_rate`, `tax_id_invalid`; notes `tax_id_missing` and `older_than_upload` (a note never
changes the status). `eval_validation.py` catch counts now ignore notes (`validate.review` drops them), so a
planted mistake caught only by a note no longer counts as caught.

**Status: stopped before the full re-runs.** One of the 6 expected catches failed live (Walmart) and one sample
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
allowed room, checked by hand: 7 small taxes where 1% is under 1 cent per line (e.g. 0.75 to 0.76 on one line),
and 2 where the planted tax became a whole number (21.00, 6.00), which gets the 0.5 room for whole-unit
currencies; 3 lowered taxes of 0.15 to 0.30 on one line are within 1 cent.

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
