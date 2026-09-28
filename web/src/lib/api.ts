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
  items: Item[];
};

export type Check = { check: string; fields: string[]; message: string; duplicate_of?: number };

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

export type DocumentDetail = DocumentRow & { mime: string; document: Doc | null; checks: Check[] | null; error: string | null };

const API = process.env.NEXT_PUBLIC_API_URL;

/** fetch() to the API with the user's access token. Throws an Error with the API's message on failure. */
export async function api(path: string, init: RequestInit = {}): Promise<Response> {
  const { data } = await createClient().auth.getSession();
  const res = await fetch(`${API}${path}`, {
    ...init,
    headers: { ...init.headers, Authorization: `Bearer ${data.session?.access_token ?? ""}` },
  });
  if (res.status === 401) {
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- expired session: full reload to the login page on purpose
    location.href = "/login";
    throw new Error("Please log in again.");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(typeof body?.detail === "string" ? body.detail : `Request failed (${res.status}). Please try again.`);
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
  URL.revokeObjectURL(url);
  return res;
}

export function money(value: string | number | null, currency?: string | null) {
  if (value === null || value === undefined) return "–";
  const n = Number(value).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return currency ? `${n} ${currency}` : n;
}
