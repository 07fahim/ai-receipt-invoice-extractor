# n8n workflows

## crosscheck-google-sheets.json
Each checked document becomes a row in a Google Sheet. Corrections update the same row. A deleted
document keeps its row with status `deleted`. A document that needs review or could not be read
sends a Telegram message and an email with a link to it.

1. Crosscheck posts an event to the webhook (`document.passed`, `document.reviewed`, `document.needs_review`,
   `document.failed`, `document.deleted`). The app keeps events in a database table until they are sent, so a
   restart loses none. It sends one event at a time per account, in order, and n8n answers only after the workflow
   has finished, so two events for the same document never race. The Account page's "Send test" event
   (`"event": "test"`) passes the signature check and writes nothing.
2. A Code node checks the HMAC-SHA256 signature (`X-Signature`) and drops anything not signed with the secret.
3. Needs review or failed: Telegram "Send message" and a Gmail "Send" (Gmail API over HTTPS; Render's free plan blocks
   SMTP ports, so an SMTP node cannot send from there). Everything else: Google Sheets "Append or Update Row", matched on `id`.
4. Each alert step fails on its own, so one channel being down never stops the other.
   WhatsApp (Meta Cloud API) was tried and paused: Meta blocks sending until the business has a payment method,
   a complete business profile and business verification.

Delivery: a failed send is retried after 1 min, 5 min, 30 min and 2 h, then dropped. Each attempt waits up to
5 minutes, because waking a sleeping n8n on Render took 113 s. While n8n is still starting up it answers 404 for a
minute or two; the retry covers that.

Known limits: the signature covers the body only, so a captured request could be sent again and re-send the same
row or alert. If an attempt times out while n8n is still working, the event is sent again and an alert can arrive
twice. Each event carries an `event_id`; drop repeats on it if that matters.

Hosting: `render.yaml` in the repo root runs n8n on Render's free plan with its data in Supabase (schema `n8n`;
run `create schema if not exists n8n;` first if n8n does not create it). Give n8n its own database login that owns
schema `n8n`, so it can't read the app's tables. That login also needs `grant create on database postgres to <login>;`:
n8n runs `create schema if not exists` at every start and stops without it. No health check is set: n8n takes
about a minute to start on the free plan, longer than Render waits, which caused a restart loop.

Setup:
- Sheet with these headers in row 1: `id file status vendor date currency subtotal tax total items checks updated`.
- A Telegram bot from @BotFather. Send it one message first, then get your chat id (for example from @userinfobot).
- Google Cloud: an OAuth client (web) with redirect URI `<n8n address>/rest/oauth2-credential/callback`,
  the Google Sheets API and Gmail API enabled. Publish the app (In production; unverified is fine for your own account):
  while it is in testing, Google sign-ins expire after 7 days and the Sheets and Gmail steps stop working.
- n8n started with `CROSSCHECK_WEBHOOK_SECRET` set, `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` and
  `NODE_FUNCTION_ALLOW_BUILTIN=crypto` (the Code node reads the secret and uses `crypto`).
  Optional `CROSSCHECK_APP_URL` (default `http://localhost:3000`): the web app address used in alert links.
- Import the file. Pick your Google Sheets, Telegram and Gmail credentials, your sheet, chat id and email address. Then activate.
- In the app's environment: `WEBHOOK_URL=<n8n>/webhook/crosscheck`, `WEBHOOK_SECRET=<same secret>`,
  `WEBHOOK_USER_ID=<the account(s) whose documents are sent, comma-separated>`.
