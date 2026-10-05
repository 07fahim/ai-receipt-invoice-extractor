import base64
import json
import os
import re
import time
import urllib.error
import urllib.request
from decimal import Decimal
from pathlib import Path

from schema import Document

ROOT = Path(__file__).parent

# name -> (api style, base url, model id, key variable, seconds between calls to stay under free limits)
MODELS = {
    'gemini-3.5-flash-lite': ('gemini', None, 'gemini-3.5-flash-lite', 'GEMINI_API_KEY', 4.5),
    'gemini-3.1-flash-lite': ('gemini', None, 'gemini-3.1-flash-lite', 'GEMINI_API_KEY', 4.5),
    'gemini-3.5-flash': ('gemini', None, 'gemini-3.5-flash', 'GEMINI_API_KEY', 13),  # second reading of flagged documents
    'gemini-3.8-flash': ('gemini', None, 'gemini-3.8-flash', 'GEMINI_API_KEY', 13),  # free tier: 5/min, 20/day
    'gemma-4-31b': ('gemini', None, 'gemma-4-31b-it', 'GEMINI_API_KEY', 10),
    'groq-qwen3.8-27b': ('openai', 'https://api.groq.com/openai/v1', 'qwen/qwen3.8-27b', 'GROQ_API_KEY', 20),
    'glm-4.6v-flash': ('openai', 'https://api.z.ai/api/paas/v4', 'glm-4.6v-flash', 'ZAI_API_KEY', 3),
    'deepseek-flash': ('openai', 'https://api.deepseek.com', 'deepseek-flash', 'DEEPSEEK_API_KEY', 1),  # paid only
    # Token Harbor free models: limits not published, so a slow pace
    'th-deepseek-v4.1-flash': ('openai', 'https://tokenharbor.ai/v1', 'deepseek-v4.1-flash:free', 'TOKENHARBOR_API_KEY', 6),
    'th-qwen3.8-flash': ('openai', 'https://tokenharbor.ai/v1', 'qwen3.8-flash:free', 'TOKENHARBOR_API_KEY', 6),
    'th-mimo-v2.6-flash': ('openai', 'https://tokenharbor.ai/v1', 'mimo-v2.6-flash:free', 'TOKENHARBOR_API_KEY', 6),
    # OpenRouter free models: 20 requests/min
    'or-inkling': ('openai', 'https://openrouter.ai/api/v1', 'thinkingmachines/inkling:free', 'OPENROUTER_API_KEY', 3.5),
    'or-dots-3-note': ('openai', 'https://openrouter.ai/api/v1', 'dots-studio/dots-3-note-preview:free', 'OPENROUTER_API_KEY', 3.5),
    'or-nemotron-omni': ('openai', 'https://openrouter.ai/api/v1', 'nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free', 'OPENROUTER_API_KEY', 3.5),
}

# thinking level per model id; "low" measured on hard cases 2026-10-03 (results/M3_NOTES.md): 5-9 s instead of 45-146 s
THINKING = {'gemini-3.5-flash': 'low'}

PROMPT = """Extract the data from this receipt or invoice image.
Return only one JSON object with exactly these keys:
is_document (false if the image is not a receipt, bill or invoice at all, e.g. a menu, a photo or a logo),
doc_type ("invoice" or "receipt"),
document_count (how many separate receipts or invoices the image shows; the pages of one invoice count as 1),
vendor (the seller's business name only, as printed, usually at the top; null if it is cut off or not printed; never a document title such as "Tax invoice" or "Provisional bill", and never a name from an advert or promotion),
branch (the store number or branch name printed with the business name, e.g. "#017314" or "Gulshan branch"; never the street address),
buyer, doc_number, issue_date (YYYY-MM-DD), due_date (YYYY-MM-DD),
issue_date_text and due_date_text (each date exactly as printed, character for character),
currency (ISO 4217 code), subtotal, discount,
tax (all taxes and duties together, e.g. VAT plus supplementary duty),
tax_included (true if the printed prices already include the tax, e.g. "VAT included"; false if it is added on top),
service_charge, total,
total_text (the total exactly as printed, character for character),
items: list of {description, quantity, unit_price, amount, discount}.
Rules:
- Use null for anything not printed on the document. Never guess or calculate a missing value;
  the only sum you make is tax when several taxes or duties are printed separately.
- Amounts are plain JSON numbers without currency symbols or thousands separators.
  Use the document's own number format to decide whether "." or "," separates thousands.
- amount is the line total as printed, before any line discount. Discounts are positive numbers.
- total is the final amount due, not the cash paid or the change.
- Include add-ons that have their own price as separate items.
- Coupons, discounts, savings, promotions and price reductions are never items, even when printed on their own line
  with a minus sign: put them in the discount of the item they belong to, or in the document discount if they apply
  to the whole bill.
- Lines that add up other lines (subtotal, "MDSE ST", net total) are never items."""


def load_env():
    f = ROOT / '.env'
    if f.exists():
        for line in f.read_text(encoding='utf-8-sig').splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"\''))


def mime(data):
    # from the first bytes, not the file name
    if data[:4] == b'%PDF':
        return 'application/pdf'
    if data[:4] == b'\x89PNG':
        return 'image/png'
    if data[:3] == b'\xff\xd8\xff':
        return 'image/jpeg'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'image/webp'
    return None


def post(url, headers, body, retries=3, timeout=60):
    # 60 s per attempt suits Gemini; slower models (GLM, Gemma) need timeout=180.
    data = json.dumps(body).encode()
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json',
                                                              'User-Agent': 'receipt-extractor/0.1', **headers})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r), attempt + 1
        except urllib.error.HTTPError as e:
            reply = e.read().decode(errors='replace')
            # Gemini names the quota window in quotaId; waiting cannot help a used-up daily quota until it resets
            daily = e.code == 429 and ('PerDay' in reply or 'Daily' in reply)
            if e.code in (429, 500, 502, 503) and attempt < retries and not daily:
                time.sleep(30 * (attempt + 1))
                continue
            raise RuntimeError(f'{"daily quota used up: " if daily else ""}HTTP {e.code}: {reply[:300]}') from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:  # no answer, DNS failure, reset
            if attempt < retries:
                time.sleep(5 * (attempt + 1))
                continue
            raise RuntimeError(f'no answer from the model service: {e}') from None


# the assistant's chat models, tried in order: a busy or failing one passes the question to the next
CHAT_MODELS = [('https://api.groq.com/openai/v1', 'qwen/qwen3.8-27b', 'GROQ_API_KEY'),
               # OpenRouter's router picks any free model that is up; single free models get withdrawn (Qwen, Kimi)
               ('https://openrouter.ai/api/v1', 'openrouter/free', 'OPENROUTER_API_KEY')]


def chat(messages, tools, tool_choice='auto'):
    errors = []
    for base, model, key_var in CHAT_MODELS:
        if not os.environ.get(key_var):
            continue
        body = {'model': model, 'temperature': 0, 'messages': messages}
        if tools:
            body |= {'tools': tools, 'tool_choice': tool_choice}
        try:
            r, _ = post(f'{base}/chat/completions', {'Authorization': f'Bearer {os.environ[key_var]}'}, body,
                        retries=0, timeout=20)
            return r['choices'][0]['message'], r.get('usage') or {}
        except (RuntimeError, KeyError, IndexError, TypeError) as e:
            errors.append(f'{model}: {e}')
    raise RuntimeError('; '.join(errors) or 'no chat model key is set')


def call(name, image, prompt=PROMPT):
    style, base, model, key_var, _ = MODELS[name]
    key = os.environ[key_var]
    b64 = base64.b64encode(image).decode()
    if style == 'gemini':
        config = {'temperature': 0}
        if model.startswith('gemini'):
            config['responseMimeType'] = 'application/json'
        if model in THINKING:
            config['thinkingConfig'] = {'thinkingLevel': THINKING[model]}
        r, attempts = post(f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',
                 {'x-goog-api-key': key},
                 {'contents': [{'parts': [{'inline_data': {'mime_type': mime(image), 'data': b64}}, {'text': prompt}]}],
                  'generationConfig': config})
        parts = r['candidates'][0]['content']['parts']
        text = ''.join(p.get('text', '') for p in parts if not p.get('thought'))
        u = r.get('usageMetadata', {})
        return text, u.get('promptTokenCount'), u.get('candidatesTokenCount'), attempts
    if mime(image) == 'application/pdf':
        raise ValueError(f'{name} does not read PDFs; use a Gemini model or send page images')
    r, attempts = post(f'{base}/chat/completions', {'Authorization': f'Bearer {key}'},
             {'model': model, 'temperature': 0, 'response_format': {'type': 'json_object'},
              'messages': [{'role': 'user', 'content': [
                  {'type': 'text', 'text': prompt},
                  {'type': 'image_url', 'image_url': {'url': f'data:{mime(image)};base64,{b64}'}}]}]})
    u = r.get('usage', {})
    return r['choices'][0]['message']['content'], u.get('prompt_tokens'), u.get('completion_tokens'), attempts


MONEY = ('subtotal', 'discount', 'tax', 'service_charge', 'total')
QUANTITY = re.compile(r'\s*(\d+(?:\.\d+)?)\s*\D*')  # a number, then an optional unit; money stays strict
ITEM_NUMBERS = ('quantity', 'unit_price', 'amount', 'discount')
VAT_FORM = re.compile(r'mushak|মূসক', re.I)  # Bangladeshi VAT form names (Mushak-6.3) printed near the branch


def parse(text):
    # numbers sent as text are rejected: "60.000" would otherwise become 60
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.S).strip()
    start = text.find('{')
    if start == -1:
        raise ValueError('no JSON object in model output')
    data, _ = json.JSONDecoder().raw_decode(text[start:])  # ignores any text after the object
    if not isinstance(data, dict) or not (set(data) & set(Document.model_fields)):
        raise ValueError('JSON has none of the expected keys')  # e.g. nested under another key
    if data.get('items') is None:
        data['items'] = []  # "null when not printed" also applies to the list
    if not all(isinstance(i, dict) for i in data['items']):
        raise ValueError('items must be objects')
    for i in data['items']:  # "২ কেজি", "1 dozen": the quantity is the number before the unit (any script's digits)
        if isinstance(i.get('quantity'), str):
            m = QUANTITY.fullmatch(i['quantity'])
            i['quantity'] = Decimal(m[1]) if m else None
    numbers = [data.get(k) for k in MONEY] + [i.get(k) for i in data['items'] for k in ITEM_NUMBERS]
    if any(isinstance(v, str) for v in numbers):
        raise ValueError('amount given as text, not a number')
    for d, keys in [(data, MONEY)] + [(i, ITEM_NUMBERS) for i in data['items']]:
        for k in keys:
            if isinstance(d.get(k), float):
                d[k] = round(d[k], 6)  # a unit price like 0.3333333 must not fail the whole document
    if not isinstance(data.get('document_count'), int) or isinstance(data.get('document_count'), bool):
        data['document_count'] = None  # a hint only: "two" or "1-2" must not fail the whole document
    if isinstance(data.get('currency'), str):
        data['currency'] = data['currency'].strip().upper() or None  # 'usd' and 'USD' are one currency
    if not isinstance(data.get('tax_included'), bool):
        data['tax_included'] = None  # unknown: the checks accept tax either added or included
    if not isinstance(data.get('is_document'), bool):
        data['is_document'] = None  # unknown counts as a document: only a clear false triggers the message
    if isinstance(data.get('branch'), str) and VAT_FORM.search(data['branch']):
        data['branch'] = None  # the form's name, not a branch
    if isinstance(data.get('doc_type'), str):
        dt = data['doc_type'].strip().lower()
        data['doc_type'] = dt if dt in ('invoice', 'receipt') else None
    return Document.model_validate(data)
