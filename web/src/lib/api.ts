import { createClient } from "@/lib/supabase/client";

export type Status = "processing" | "passed" | "needs_review" | "failed" | "reviewed";

export type Item = {
  description: string | null;
  quantity: string | null;
  unit_price: string | null;
  amount: string | null;
  discount: string | null;
};

// Money and quantities arrive as text ("60.00") so amounts are never rounded in the browser.
export type Doc = {
  doc_type: "invoice" | "receipt" | null;
  vendor: string | null;
  branch: string | null;
  buyer: string | null;
  doc_number: string | null;
  issue_date: string | null;
  due_date: string | null;
  issue_date_text: string | null;
  due_date_text: string | null;
  currency: string | null;
  subtotal: string | null;
  discount: string | null;
  tax: string | null;
  service_charge: string | null;
  total: string | null;
  total_text?: string | null;
  tax_rate?: string | null;
  seller_tax_id?: string | null;
  items: Item[];
};

export type Check = { check: string; fields: string[]; message: string; duplicate_of?: number; level?: "note" };

// A fix worked out from the numbers (e.g. 280 read for 240): shown in review, applied only when the user clicks.
export type Suggestion = { message: string; changes: { field: string; from: string; to: string }[] };

/** One field where a second AI reading differs. `to` is a list of lines when the number of lines differs. */
export type SecondChange = { field: string; from: string | null; to: string | Item[]; text?: string | null };

export type DocumentRow = {
  id: number;
  file_name: string;
  status: Status;
  vendor: string | null;
  currency: string | null;
  issue_date: string | null;
  total: number | null;
  created_at: string;
};

export type DocumentDetail = DocumentRow & {
  mime: string; document: Doc | null; checks: Check[] | null; error: string | null; suggestion?: Suggestion | null; second_reading?: SecondChange[]; second_read?: boolean; updated_at: string;
};

const API = process.env.NEXT_PUBLIC_API_URL;

/** fetch() to the API with the user's access token. Throws an Error with the API's message on failure. */
export async function api(path: string, init: RequestInit = {}): Promise<Response> {
  const { data } = await createClient().auth.getSession();
  const res = await fetch(`${API}${path}`, {
    ...init,
    headers: { ...init.headers, Authorization: `Bearer ${data.session?.access_token ?? ""}` },
  });
  if (res.status === 401) {
    await createClient().auth.signOut({ scope: "local" }); // else a session the API rejects loops login -> app -> login
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- expired session: full reload to the login page on purpose
    location.href = "/login";
    throw new Error("Please log in again.");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail = body?.detail;
    // a 422 lists the fields it rejected, e.g. a total typed as "12,50"
    const field = Array.isArray(detail) && detail[0] ? `${String(detail[0].loc?.at(-1) ?? "a field")}: ${detail[0].msg}` : null;
    throw new Error(typeof detail === "string" ? detail : field ? `Check ${field}` : `Request failed (${res.status}). Please try again.`);
  }
  return res;
}

export async function getJSON<T>(path: string): Promise<T> {
  return (await api(path)).json();
}

export async function sendJSON<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await api(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return res.status === 204 ? (undefined as T) : res.json();
}

/** Save a file the API returns (exports) under its own name. */
export async function download(path: string, fallbackName: string) {
  const res = await api(path);
  const name = /filename="?([^";]+)"?/.exec(res.headers.get("Content-Disposition") ?? "")?.[1] ?? fallbackName;
  const url = URL.createObjectURL(await res.blob());
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000); // some browsers cancel a download revoked at once
  return res;
}

export function money(value: string | number | null, currency?: string | null) {
  if (value === null || value === undefined) return "–";
  // 2 decimals, 3 for currencies such as KWD
  const n = Number(value).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 3 });
  return currency ? `${n} ${currency}` : n;
}
