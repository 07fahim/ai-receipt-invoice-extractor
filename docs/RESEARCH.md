# Research: AI Receipt & Invoice Extractor (2026-09-28)

Two research passes were done before the PRD: buyer demand from our own Upwork sample, and a web check of datasets, OCR tools and model prices on primary sources. Anything not confirmed is marked **UNVERIFIED**.

## 1. Buyer demand (Upwork sample)

Source: 593 Upwork jobs scraped 2026-09-27 (`D:\Myself\Stage1_Market_Research.xlsx`, raw data in `%TEMP%\upw_clean.json`). Descriptions were cut at ~700 characters, so counts are minimums. Single 2.5-day snapshot.

- Core document-extraction jobs: **12 of 593 (~2%)**. Another 8 include extraction as part of a bigger platform. RAG "chat with documents" jobs are more common and better paid, but are a different use case (project 3).
- Budgets (12 core jobs): hourly $10–40/hr (median band $15–35); fixed $50, $100, $2,000 (n=3, too few for a median). Wider "RAG & document AI" group: 31 jobs, fixed median $300 (n=9), hourly median $35.

| What | Counts (core 12) |
|---|---|
| Document types | invoices 6, contracts 2, receipts 1, purchase orders 1, credit memos 1, bank/merchant statements 1, forms + IDs 1, medical PDFs 1, vendor compliance docs 1, mixed scanned docs with tables 2 |
| Input | PDF upload in most; email 2 (Gmail, Microsoft 365); scans 2; Google Drive 0; WhatsApp 0 |
| Output | QuickBooks 3, Google Sheets 1, FileMaker 1, UiPath 1, dashboard/analyst tool 2 |
| Stack named | Python 4, LLM 3 (no model named), OCR 3 (no engine named), AWS 2 |

Things buyers ask for again and again: **accuracy measured against a verified test set**, checking extracted values against the source, and a **human review step**. Volume and languages are rarely stated.

Caveat: three near-identical "invoice PDFs to QuickBooks" posts ($15–35/hr) look like one client reposting, which inflates the invoice and QuickBooks counts.

**Takeaway:** lead with invoices (receipts second), PDF/upload plus email in, Google Sheets / Excel / QuickBooks-ready out, and show a measured accuracy table and a review screen.

## 2. Evaluation datasets

| Dataset | Licence | Size / test split | Line items, subtotal, tax? | Notes | Source |
|---|---|---|---|---|---|
| **CORD-v2** | CC-BY-4.0 | 1,000 (800/100/**100**) | Yes, yes, yes (plus service charge, discounts) | Real photos, Indonesian + some English, **no currency field** | https://huggingface.co/datasets/naver-clova-ix/cord-v2 |
| SROIE (ICDAR 2019) | **UNVERIFIED** (no official licence found) | 626 train / 347 test | No; company, date, address, total only | Known label errors; corrected copies exist | https://rrc.cvc.uab.es/?ch=13 , https://github.com/zzzDavid/ICDAR-2019-SROIE |
| FATURA | CC-BY-4.0 | 10,000 from **50 templates** | Yes (layout-level) | Synthetic invoices, low variety | https://zenodo.org/records/8261508 |
| Voxel51 invoice images | ODbL | 8,181 (1,489 annotated) | Yes | Synthetic invoices | https://huggingface.co/datasets/Voxel51/high-quality-invoice-images-for-ocr |
| CORU / ReceiptSense | MIT | 20,000 (3.7k test) | Items yes | Arabic 54% / English 26% | https://huggingface.co/datasets/abdoelsayed/CORU |
| katanaml invoices-donut-data-v1 | MIT tag, image origin not stated | 500 | Yes | | https://huggingface.co/datasets/katanaml-org/invoices-donut-data-v1 |

Label noise: arXiv 2512.09666 relabelled CORD and SROIE; even after relabelling only 95.5% of SROIE documents pass arithmetic checks, because some real receipts are themselves wrong. This supports a validation layer that flags instead of trusting.

**Decision:** CORD-v2 test split (100) is the headline benchmark. Add ~30 invoices from Voxel51 or FATURA for invoice coverage. SROIE is optional (licence unclear).

## 3. Local OCR and models on this laptop (GTX 1050, 4 GB, Pascal)

- PyTorch 2.8+ CUDA 12.8/12.9 wheels dropped Pascal; only **cu126** wheels still support sm_61. Pin `--index-url https://download.pytorch.org/whl/cu126` or run on CPU. (https://github.com/pytorch/pytorch/issues/157517)
- **RapidOCR** (Apache-2.0, PaddleOCR models as ONNX, `pip install rapidocr onnxruntime`, Windows + CPU OK): the realistic local OCR. https://github.com/RapidAI/RapidOCR
- PaddleOCR 3.7 (PP-OCRv6): Windows GPU support on Pascal **UNVERIFIED**.
- docTR 1.1 (Apache-2.0): CPU OK, alternative. EasyOCR: last release Sep 2024. Tesseract 5.5: easy install, expected weakest on photos (not measured).
- Small VLMs: Donut fine-tuned on CORD-v2 (MIT) is a useful local baseline only. Qwen2.5-VL-3B has a research licence and its fit on 4 GB is **UNVERIFIED**. Not the main path.
- OCR quality on receipts was **not measured** for any tool. M1 measures it on CORD.

## 4. Hosted vision LLMs (official pricing pages, read 2026-09-28)

Per-receipt cost is my own arithmetic for a ~1000×1500 px image, ~500 prompt tokens and ~500 output tokens. It is an estimate, not a measurement.

| Model | Input / output per 1M tokens | Est. cost per receipt |
|---|---|---|
| Gemini 3.1 Flash-Lite | $0.25 / $1.50 | ~$0.001 |
| Gemini 3.8 Flash | $0.75 / $3.75 until 2026-12-31, then double | ~$0.003 |
| OpenAI gpt-5-mini | $0.25 / $2.00 | ~$0.002 (plus reasoning tokens) |
| Claude Haiku 4.5 | $1 / $5 | ~$0.005 |

- Gemini **free tier**: prompts and outputs are used to improve Google products and may be read by human reviewers (https://ai.google.dev/gemini-api/terms). Fine for public datasets; the demo UI must warn users not to upload private documents on the free tier. Free-tier rate limits: **UNVERIFIED**.
- Sources: https://ai.google.dev/gemini-api/docs/pricing , https://developers.openai.com/api/docs/pricing , https://platform.claude.com/docs/en/about-claude/pricing

## 5. Competition (open-source demos)

- katanaml/sparrow (GPL-3.0): full platform around local vision LLMs.
- ANAND9051/invoice-receipt-extractor: Streamlit + Gemini, offline RapidOCR mode.
- 01adityakumarsingh/Invoice-OCR-Extractor: OCR + Claude/Groq, FastAPI + Streamlit, SROIE scoring.

Most demos are "Streamlit + GPT, JSON out" with no measured results. Ways to stand out:
1. Published per-field accuracy table on CORD-v2, comparing 2+ approaches, with cost per document.
2. Arithmetic validation that sends records to review, with a measured catch rate.
3. Honest notes on dataset label noise.
4. Review screen next to the original, and clean CSV/XLSX export.

## Still unverified
SROIE licence; PaddleOCR GPU on Pascal; Florence-2; Gemini free-tier rate limits; gpt-5-nano image support; OCR quality of every tool on receipts.
