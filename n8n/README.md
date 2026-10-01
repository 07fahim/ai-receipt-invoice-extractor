# n8n workflows

## crosscheck-google-sheets.json
Each checked document becomes a row in a Google Sheet. Corrections update the same row. A deleted
document keeps its row with status `deleted`. A document that needs review or could not be read
sends a Telegram message and an email with a link to it.

1. Crosscheck posts an event to the webhook (`document.passed`, `document.reviewed`, `document.needs_review`,
   `document.failed`, `document.deleted`). The app sends one event at a time, in order, and n8n answers only after
   the workflow has finished, so two events for the same document never race.
2. A Code node checks the HMAC-SHA256 signature (`X-Signature`) and drops anything not signed with the secret.
3. Needs review or failed: Telegram "Send message" and a Gmail "Send" (Gmail API over HTTPS; Render's free plan blocks
   SMTP ports, so an SMTP node cannot send from there). Everything else: Google Sheets "Append or Update Row", matched on `id`.
4. Each alert step fails on its own, so one channel being down never stops the other.
   WhatsApp (Meta Cloud API) was tried and paused: Meta blocks sending until the business has a payment method,
   a complete business profile and business verification.

Known limit: the signature covers the body only. A captured request could be sent again, which re-sends the same
row or alert. Add a timestamp to the payload if that matters.

Hosting: `render.yaml` in the repo root runs n8n on Render's free plan with its data in Supabase (schema `n8n`).

Setup:
- Sheet with these headers in row 1: `id file status vendor date currency subtotal tax total items checks updated`.
- A Telegram bot from @BotFather. Send it one message first, then get your chat id (for example from @userinfobot).
- Google Cloud: an OAuth client (web) with redirect URI `<n8n address>/rest/oauth2-credential/callback`,
  the Google Sheets API and Gmail API enabled, and your account added as a test user while the app is in testing.
- n8n started with `CROSSCHECK_WEBHOOK_SECRET` set, `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` and
  `NODE_FUNCTION_ALLOW_BUILTIN=crypto` (the Code node reads the secret and uses `crypto`).
  Optional `CROSSCHECK_APP_URL` (default `http://localhost:3000`): the web app address used in alert links.
- Import the file. Pick your Google Sheets, Telegram and Gmail credentials, your sheet, chat id and email address. Then activate.
- In the app's environment: `WEBHOOK_URL=<n8n>/webhook/crosscheck`, `WEBHOOK_SECRET=<same secret>`,
  `WEBHOOK_USER_ID=<the account whose documents are sent>`.
