# PRD: AI Receipt & Invoice Extractor v0.1

Status: draft for approval, 2026-09-28. Replaces `docs/old/AI_Receipt_Invoice_Extractor_Full_MVP_Spec.docx` (kept for reference; its full SaaS scope is not the plan for v0.1).
Evidence behind this PRD: `docs/RESEARCH.md`.

## 1. Problem and target buyer

Small businesses, bookkeepers and operations teams retype invoices and receipts into spreadsheets or accounting tools. It is slow and mistakes slip through.

This project is a **portfolio piece**, not a SaaS. It has to prove to buyers on Fiverr (gig 2, Document AI) and Upwork (document extraction jobs) that I can:
- pull the right fields out of messy real documents,
- show how accurate that is with measured numbers,
- catch wrong values before they reach the buyer's books.

In the Upwork sample, invoices were requested far more often than receipts (6 jobs vs 1), so the product handles both but leads with invoices in the demo and README.

## 2. v0.1 scope: the core loop

```
Upload (image or PDF, several files at once)
  -> PDF pages to images
  -> Extraction to strict JSON (provider can be swapped)
  -> Deterministic validation
  -> Review screen: original on the left, editable fields on the right, flagged fields highlighted
  -> Export CSV / XLSX
```

### Fields
| Group | Fields |
|---|---|
| Document | doc_type (invoice / receipt), vendor (seller) name, buyer name, invoice or receipt number, issue date, due date, currency |
| Amounts | subtotal, discount, tax, service charge, total |
| Line items | description, quantity, unit price, amount, line discount |

Missing fields are `null`. The model must never guess a value that is not on the page.

### Validation (deterministic code, no AI)
Built and measured in M2 (`results/M2_NOTES.md`):
1. Line items (after line discounts) add up to the subtotal, exactly. Without a subtotal, lines must add up to the total.
2. subtotal + tax + service charge − discount = total; only the total may be cash-rounded (up to 0.05%).
3. quantity × unit price = line amount.
4. Issue date not in the future; due date not before issue date.
5. Currency is a valid ISO 4217 code (when present).
6. Total is present, and a document with amounts has line items.

Each failed check names the fields involved, so the review screen can highlight them. A document with any failed check gets status **needs review**; otherwise **passed**. The status comes from these checks, not from the model rating its own confidence.

## 3. Out of scope for v0.1

| Left out | Why |
|---|---|
| Login / accounts | A demo does not need them; adds a week |
| Categories, rules, dashboard, history search | Not what the buyers in the sample asked for |
| Currency conversion | Store the original currency only |
| QuickBooks / Xero connection | Needs real buyer demand first (v0.2) |
| Mobile app, team accounts | Far beyond a portfolio piece |
| Training or fine-tuning a model | Hosted models plus validation are enough to prove the loop |

## 4. v0.2 candidates (only after v0.1 ships)
1. **Email in via n8n:** Gmail attachment → this API → Google Sheets row, with "needs review" rows marked. Matches 2 email jobs in the sample and the n8n skill I already have.
2. QuickBooks-ready export format (3 jobs in the sample asked for QuickBooks).

## 5. Extraction design

- One function: `extract(pages) -> Document` (Pydantic model). Each provider is one small module behind it, chosen by a setting in `.env`.
- Two approaches are compared in the evaluation:
  - **A. Local OCR + LLM:** RapidOCR reads the text on the laptop, an LLM turns the text into JSON.
  - **B. Vision LLM:** the page image goes straight to a vision model.
- Structured output (JSON schema) is used wherever the provider supports it. The output is checked against the Pydantic model; a failed parse counts as a failed extraction, never silently fixed.
- Which model ships in the demo is decided by the evaluation (accuracy, cost, speed), after the API key choice.

## 6. Stack

| Part | Choice |
|---|---|
| Backend | Python, FastAPI, Pydantic |
| OCR | RapidOCR (ONNX, runs on CPU) |
| PDF to image | pypdfium2 |
| Review UI | One page of static HTML + JavaScript served by FastAPI. Move to Next.js only if the demo looks weak |
| Storage | SQLite (extraction runs and results); uploaded files on local disk |
| Export | csv (standard library), openpyxl |
| Packaging | Docker for the demo |
| Hosting | A free host, chosen when deploying (options not checked yet) |

## 7. Data

Canonical output:
```json
{
  "doc_type": "invoice",
  "vendor": "ABC Supplies Ltd",
  "buyer": "Green Cafe",
  "doc_number": "INV-19283",
  "issue_date": "2026-09-18",
  "due_date": "2026-10-18",
  "currency": "USD",
  "subtotal": 850.00,
  "tax": 127.50,
  "discount": 0.00,
  "service_charge": 0.00,
  "total": 977.50,
  "items": [
    {"description": "Paper cups (box)", "quantity": 2, "unit_price": 350.00, "amount": 700.00},
    {"description": "Napkins", "quantity": 1, "unit_price": 150.00, "amount": 150.00}
  ]
}
```

`extraction_runs` table: id, file name, provider, model, approach (A/B), status, latency_ms, input_tokens, output_tokens, estimated_cost, raw response, validation results, edited result, created_at.

## 8. Evaluation plan

| Item | Detail |
|---|---|
| Data | CORD-v2 test split (100 real receipts) + ~30 invoices from Voxel51 or FATURA |
| Field accuracy | Per field, after normalising (numbers to 2 decimals, dates to ISO, text trimmed and case-folded) |
| Line items | Precision / recall / F1 on matched items |
| Validation | Pass rate, and **catch rate**: of documents with a wrong field, how many did validation flag |
| Cost and speed | Cost per document (from token counts and published prices), latency per document |
| Comparison | At least approach A vs approach B, plus the Donut-CORD model as a local baseline if time allows |

Rules:
- Only measured numbers go into the README. No number is written down before it is measured.
- CORD has no currency field, so currency is scored on invoices only.
- Known label errors in the datasets are reported, not hidden.

## 9. Privacy and security
- Check file type and size on upload; never run uploaded files.
- API keys only in a local `.env`; `.env` is in `.gitignore`; an `.env.example` without values is committed.
- If a free-tier model is used, the UI says so and tells users not to upload private documents.
- Public datasets and my own sample documents only. Nothing from my employers.
- Uploaded files can be deleted from the demo.

## 10. Definition of done (v0.1)
- Public GitHub repo with a README: what it does, architecture diagram, measured accuracy table, cost per document, screenshots, how to run.
- 60–90 second demo video: upload, a flagged field, a fix, the export.
- Live demo link if a free host allows it.
- One command to run locally (`docker compose up` or `uvicorn`).
- Fiverr gig 2 cover replaced with a real screenshot.

## 11. Milestones (12–15 h/week; time is an estimate)

| # | Milestone | Needs API key? | Done when |
|---|---|---|---|
| M1 | Dataset loader + evaluation script + RapidOCR baseline | No | OCR text quality on CORD test is measured and saved |
| M2 | Pydantic schema + validation checks + tests | No | All checks pass unit tests on hand-made good and bad samples; catch rate measurable on ground truth with injected errors |
| M3 | Providers for approach A and B + full evaluation run | Yes | Accuracy / cost / latency table for both approaches |
| M4 | FastAPI endpoints + review page + CSV/XLSX export | Yes (for live extraction) | A file goes from upload to export in the browser |
| M5 | README, video, Docker, deploy | Yes | Definition of done above is met |

M1 and M2 can start now without a key.

## 12. Open decisions
1. **LLM API key** (Gemini / OpenAI / Claude): deferred by the user. Needed from M3.
2. **Front end:** static page (recommended) or Next.js.
3. **Free host** for the live demo.
