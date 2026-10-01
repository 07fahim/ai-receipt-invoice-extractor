# n8n workflows

## crosscheck-google-sheets.json
Each checked document becomes a row in a Google Sheet. Corrections update the same row. A deleted
document keeps its row with status `deleted`.

1. Crosscheck posts an event to the webhook (`document.passed`, `document.reviewed`, `document.deleted`).
2. A Code node checks the HMAC-SHA256 signature (`X-Signature`) and drops anything not signed with the secret.
3. Google Sheets "Append or Update Row", matched on `id`.

Setup:
- Sheet with these headers in row 1: `id file status vendor date currency subtotal tax total items checks updated`.
- n8n started with `CROSSCHECK_WEBHOOK_SECRET` set, `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` and
  `NODE_FUNCTION_ALLOW_BUILTIN=crypto` (the Code node reads the secret and uses `crypto`).
- Import the file, pick your Google Sheets credential and sheet, then activate.
- In the app's `.env`: `WEBHOOK_URL=<n8n>/webhook/crosscheck`, `WEBHOOK_SECRET=<same secret>`,
  `WEBHOOK_USER_ID=<the account whose documents are sent>`.
