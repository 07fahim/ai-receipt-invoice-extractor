# n8n workflows

## crosscheck-google-sheets.json
Each checked document becomes a row in a Google Sheet. Corrections update the same row. A deleted
document keeps its row with status `deleted`. A document that needs review or could not be read
sends a Telegram message and an email with a link to it.

1. Crosscheck posts an event to the webhook (`document.passed`, `document.reviewed`, `document.needs_review`,
   `document.failed`, `document.deleted`). The app sends one event at a time, in order, and n8n answers only after
   the workflow has finished, so two events for the same document never race.
2. A Code node checks the HMAC-SHA256 signature (`X-Signature`) and drops anything not signed with the secret.
3. Needs review or failed: Telegram "Send message" and an email (SMTP, e.g. Gmail with an app password).
   Everything else: Google Sheets "Append or Update Row", matched on `id`.
4. A WhatsApp step (template `crosscheck_alert`) sits next to Telegram but is disabled. Meta blocks sending until the
   business has a payment method, a complete business profile and business verification. Each alert step fails on its
   own, so one channel being down never stops the others.

Known limit: the signature covers the body only. A captured request could be sent again, which re-sends the same
row or alert. Add a timestamp to the payload if that matters.

Setup:
- Sheet with these headers in row 1: `id file status vendor date currency subtotal tax total items checks updated`.
- A Telegram bot from @BotFather. Send it one message first, then get your chat id (for example from @userinfobot).
- For email: an SMTP credential (Gmail: `smtp.gmail.com`, port 465, SSL, an app password).
- n8n started with `CROSSCHECK_WEBHOOK_SECRET` set, `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` and
  `NODE_FUNCTION_ALLOW_BUILTIN=crypto` (the Code node reads the secret and uses `crypto`).
  Optional `CROSSCHECK_APP_URL` (default `http://localhost:3000`): the web app address used in alert links.
- Import the file. Pick your Google Sheets, Telegram and SMTP credentials, your sheet, chat id and email address. Then activate.
- In the app's `.env`: `WEBHOOK_URL=<n8n>/webhook/crosscheck`, `WEBHOOK_SECRET=<same secret>`,
  `WEBHOOK_USER_ID=<the account whose documents are sent>`.
