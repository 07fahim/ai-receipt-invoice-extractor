"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, RotateCw, Trash2, X, ZoomIn, ZoomOut } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { StatusBadge } from "@/components/status-badge";
import { api, getJSON, sendJSON, type Check, type Doc, type DocumentDetail, type DocumentRow, type Item, type Suggestion } from "@/lib/api";
import { cn } from "@/lib/utils";

type Order = "MDY" | "DMY";

// The kinds of checks shown to the user, and the API checks that belong to each.
const CHECK_GROUPS: [string, string[]][] = [
  ["Line items match subtotal", ["items_sum", "items_total"]],
  ["Subtotal + tax = total", ["total_math"]],
  ["Total read as printed", ["total_format"]],
  ["Quantity × price = amount", ["line_math"]],
  ["Dates are valid", ["date_future", "due_before_issue"]],
  ["Currency is valid", ["currency_code"]],
  ["Total and line items present", ["total_present", "items_missing"]],
  ["Not a duplicate", ["duplicate"]],
  ["One document per file", ["one_document"]],
  ["Looks like a receipt or invoice", ["is_document"]],
];

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** Label for a printed date read in one order, e.g. "1 Sep 2016". Display only; the API re-reads the date. */
function readAs(text: string | null, order: Order) {
  const m = /\b(\d{1,2})[./-](\d{1,2})[./-](\d{4}|\d{2})\b/.exec(text ?? "");
  if (!m) return "";
  const [a, b, y] = [Number(m[1]), Number(m[2]), Number(m[3])];
  const [month, day] = order === "MDY" ? [a, b] : [b, a];
  return `${day} ${MONTHS[month - 1]} ${y < 100 ? y + 2000 : y}`;
}

const blank = (v: string) => (v.trim() === "" ? null : v.trim());
const EMPTY_ITEM: Item = { description: null, quantity: null, unit_price: null, amount: null, discount: null };

export default function ReviewPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [detail, setDetail] = useState<DocumentDetail | null>(null);
  const [doc, setDoc] = useState<Doc | null>(null);
  const [checks, setChecks] = useState<Check[]>([]);
  const [suggestion, setSuggestion] = useState<Suggestion | null>(null);
  const [checkError, setCheckError] = useState<string | null>(null);
  const [order, setOrder] = useState<Order | null>(null);
  const [applyToVendor, setApplyToVendor] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [confirm, setConfirm] = useState<null | "save" | "read" | "delete">(null);
  const [queue, setQueue] = useState<number[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  // load the document; poll while it is being read
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    let left = false; // the page closed while a request was running: don't poll again
    const load = () =>
      getJSON<DocumentDetail>(`/documents/${id}`)
        .then((d) => {
          if (left) return;
          setDetail(d);
          if (d.status === "processing") timer = setTimeout(load, 2000);
          else if (d.document) {
            setDoc(d.document);
            setChecks(d.checks ?? []);
            setSuggestion(d.suggestion ?? null);
            setOrder(null);
            setDirty(false);
          }
        })
        .catch((e) => setLoadError(e.message));
    load();
    getJSON<DocumentRow[]>("/documents?status=needs_review&limit=200")
      .then((rows) => setQueue(rows.map((r) => r.id).reverse())) // oldest first
      .catch(() => {});
    return () => {
      left = true;
      clearTimeout(timer);
    };
  }, [id]);

  // live checks while editing (the same checks the API runs on save)
  const firstRun = useRef(true);
  useEffect(() => {
    if (!doc) return;
    if (firstRun.current) {
      firstRun.current = false;
      return;
    }
    let stale = false; // a newer edit came in: an older answer must not overwrite the newer one
    const timer = setTimeout(() => {
      sendJSON<{ document: Doc; checks: Check[]; suggestion: Suggestion | null }>("POST", `/check?doc_id=${id}${order ? `&date_order=${order}` : ""}`, doc)
        .then((r) => {
          if (stale) return;
          setCheckError(null);
          setChecks(r.checks);
          setSuggestion(r.suggestion);
          if (order && r.document.issue_date !== doc.issue_date) setDoc((d) => d && { ...d, issue_date: r.document.issue_date, due_date: r.document.due_date });
        })
        .catch((e) => {
          if (stale) return;
          setCheckError(e.message); // never leave old ticks on screen as if they were current
          setSuggestion(null);
        });
    }, 400);
    return () => {
      stale = true;
      clearTimeout(timer);
    };
  }, [doc, order, id]);

  // closing or reloading the tab with unsaved edits asks first
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    addEventListener("beforeunload", warn);
    return () => removeEventListener("beforeunload", warn);
  }, [dirty]);

  // leaving for another document with unsaved edits asks first
  function leaveCheck(e: React.MouseEvent) {
    if (dirty && !window.confirm("Leave without saving your changes?")) e.preventDefault();
  }

  const failed = new Set(checks.map((c) => c.check));
  const flagged = new Set(checks.flatMap((c) => c.fields));
  const dateUnclear = failed.has("date_ambiguous") && !order;
  // keep the date-format choice on screen once made (the check then passes), so it can be changed
  const dateChoice = failed.has("date_ambiguous") || order !== null;
  const otherFailing = checks.filter((c) => c.check !== "date_ambiguous");

  function edit(patch: Partial<Doc>) {
    setDoc((d) => d && { ...d, ...patch });
    setDirty(true);
  }
  // fills in the suggested values; nothing is saved until the user saves
  function applySuggestion(s: Suggestion) {
    // only onto the values it was worked out from: after an edit it waits for the next check
    const current = (field: string) => {
      const m = field.match(ITEM_FIELD);
      const it = m && doc?.items[Number(m[1])];
      return m ? (it ? (it as Record<string, string | null>)[m[2]] : undefined) : (doc as unknown as Record<string, string | null>)?.[field];
    };
    if (!s.changes.every((c) => current(c.field) === c.from)) {
      toast.error("The document changed. Wait a moment for the checks to update.");
      return;
    }
    setDoc((d) => {
      if (!d) return d;
      const next = { ...d, items: d.items.map((it) => ({ ...it })) };
      for (const c of s.changes) {
        const m = c.field.match(ITEM_FIELD);
        if (m) (next.items[Number(m[1])] as Record<string, string | null>)[m[2]] = c.to;
        else (next as unknown as Record<string, string | null>)[c.field] = c.to;
      }
      return next;
    });
    setDirty(true);
  }

  function editItem(n: number, patch: Partial<Item>) {
    setDoc((d) => d && { ...d, items: d.items.map((it, i) => (i === n ? { ...it, ...patch } : it)) });
    setDirty(true);
  }

  async function save() {
    if (!doc) return;
    setConfirm(null);
    setSaving(true);
    try {
      if (order && applyToVendor && doc.vendor) {
        await sendJSON("PUT", `/vendors/${encodeURIComponent(doc.vendor)}/date-order`, { date_order: order });
      }
      await sendJSON("PUT", `/documents/${id}${order ? `?date_order=${order}` : ""}`, doc);
      toast.success("Review saved");
      const next = queue.filter((q) => q !== Number(id))[0];
      router.push(next ? `/app/documents/${next}` : "/app/documents");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not save.");
    } finally {
      setSaving(false);
    }
  }

  async function readAgain() {
    setConfirm(null);
    try {
      await sendJSON("POST", `/documents/${id}/retry`);
      location.reload(); // shows "Reading…" and polls until the new reading is in
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not read the document again.");
    }
  }

  async function remove() {
    setConfirm(null);
    try {
      await sendJSON("DELETE", `/documents/${id}`);
      toast.success("Document deleted");
      router.push("/app/documents");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not delete.");
    }
  }

  if (loadError) return <p className="text-bad">{loadError}</p>;
  if (!detail) return <p className="text-muted-foreground">Loading…</p>;

  const pos = queue.indexOf(Number(id));
  const canReadAgain = detail.status === "failed" || detail.status === "needs_review";
  const itemsTotal = doc?.items.reduce((s, i) => s + Number(i.amount ?? 0) - Math.abs(Number(i.discount ?? 0)), 0) ?? 0;

  return (
    <div>
      <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="truncate text-2xl font-semibold tracking-tight">{doc?.vendor || detail.file_name}</h1>
            <StatusBadge status={detail.status} />
          </div>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {[doc?.doc_type && doc.doc_type[0].toUpperCase() + doc.doc_type.slice(1), detail.file_name].filter(Boolean).join(" · ")}
          </p>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-3">
          {pos >= 0 && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              {pos + 1} of {queue.length}
              <Button variant="outline" size="icon" aria-label="Previous document" disabled={pos === 0} asChild={pos > 0}>
                {pos > 0 ? <Link href={`/app/documents/${queue[pos - 1]}`} onClick={leaveCheck}><ArrowLeft /></Link> : <ArrowLeft />}
              </Button>
              <Button variant="outline" size="icon" aria-label="Next document" disabled={pos === queue.length - 1} asChild={pos < queue.length - 1}>
                {pos < queue.length - 1 ? <Link href={`/app/documents/${queue[pos + 1]}`} onClick={leaveCheck}><ArrowRight /></Link> : <ArrowRight />}
              </Button>
            </div>
          )}
          {doc && (
            <Button
              className="h-9"
              disabled={saving || dateUnclear}
              aria-describedby={dateUnclear ? "save-why" : undefined}
              onClick={() => (otherFailing.length ? setConfirm("save") : save())}
            >
              {saving ? "Saving…" : "Save review"}
            </Button>
          )}
          {dateUnclear && <span id="save-why" className="basis-full text-right text-xs text-muted-foreground">Confirm the date format first</span>}
        </div>
      </div>

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(280px,1fr)_minmax(380px,1.2fr)_260px] lg:grid-cols-[1fr_1.25fr]">
        <Viewer id={id} mime={detail.mime} fileName={detail.file_name} onReadAgain={canReadAgain ? () => (dirty ? setConfirm("read") : readAgain()) : undefined} onDelete={() => setConfirm("delete")} />

        {detail.status === "processing" && <Panel className="p-6 text-muted-foreground">Reading the document…</Panel>}
        {detail.status === "failed" && (
          <Panel className="p-6">
            <p className="font-medium">This file could not be read.</p>
            <p className="mt-1 text-sm text-muted-foreground">{detail.error}</p>
            <Button className="mt-4" onClick={readAgain}>Read again</Button>
          </Panel>
        )}

        {doc && (
          <form className="rounded-xl border bg-card px-5 shadow-xs" onSubmit={(e) => e.preventDefault()} aria-label="Document fields">
            <Group title="Details">
              <div className="grid gap-x-4 gap-y-3.5 sm:grid-cols-2">
                <FieldBox label="Type" id="doc_type">
                  <select
                    id="doc_type"
                    className={inputClass}
                    value={doc.doc_type ?? ""}
                    onChange={(e) => edit({ doc_type: (e.target.value || null) as Doc["doc_type"] })}
                  >
                    <option value="">Not set</option>
                    <option value="receipt">Receipt</option>
                    <option value="invoice">Invoice</option>
                  </select>
                </FieldBox>
                <Text label={doc.doc_type === "invoice" ? "Invoice number" : "Receipt number"} id="doc_number" doc={doc} edit={edit} flagged={flagged} />
                <Text label="Vendor" id="vendor" doc={doc} edit={edit} flagged={flagged} />
                <Text label="Branch" id="branch" doc={doc} edit={edit} flagged={flagged} />
                <div className="sm:col-span-2">
                  <FieldBox label="Issue date" id="issue_date">
                    <input
                      id="issue_date"
                      type="date"
                      className={cn(inputClass, (dateUnclear || flagged.has("issue_date")) && flagClass)}
                      value={dateUnclear ? "" : doc.issue_date ?? ""}
                      disabled={dateUnclear}
                      aria-describedby={dateUnclear ? "date-why" : undefined}
                      onChange={(e) => edit({ issue_date: e.target.value || null })}
                    />
                  </FieldBox>
                  {dateChoice && (
                    <fieldset id="date-why" className="mt-2 rounded-lg border border-[#FCD34D] bg-[#FFFBEB] px-3 pt-1 pb-3 text-[13px]">
                      <legend className="px-1 font-semibold text-warn">&ldquo;{doc.issue_date_text}&rdquo; can be read two ways</legend>
                      <div className="my-1.5 flex flex-wrap gap-2">
                        {(["MDY", "DMY"] as Order[]).map((o) => (
                          <label
                            key={o}
                            className={cn(
                              "flex cursor-pointer items-center gap-1.5 rounded-md border border-input bg-card px-2.5 py-1.5",
                              order === o && "border-primary ring-1 ring-primary",
                            )}
                          >
                            <input type="radio" name="order" checked={order === o} onChange={() => { setOrder(o); setDirty(true); }} />
                            {o === "MDY" ? "Month first" : "Day first"}: {readAs(doc.issue_date_text, o)}
                          </label>
                        ))}
                      </div>
                      {doc.vendor && (
                        <label className="flex items-start gap-2 text-foreground/80">
                          <input type="checkbox" className="mt-0.5" checked={applyToVendor} onChange={(e) => setApplyToVendor(e.target.checked)} />
                          Use this format for all {doc.vendor} documents
                        </label>
                      )}
                    </fieldset>
                  )}
                </div>
                {doc.doc_type === "invoice" && (
                  <FieldBox label="Due date" id="due_date">
                    <input id="due_date" type="date" className={cn(inputClass, flagged.has("due_date") && flagClass)} value={doc.due_date ?? ""} onChange={(e) => edit({ due_date: e.target.value || null })} />
                  </FieldBox>
                )}
                <Text label="Currency" id="currency" doc={doc} edit={edit} flagged={flagged} list="currencies" />
                <Text label="Buyer" id="buyer" doc={doc} edit={edit} flagged={flagged} />
                <datalist id="currencies">
                  {["USD", "BDT", "INR", "EUR", "GBP", "IDR", "AED", "SAR"].map((c) => <option key={c} value={c} />)}
                </datalist>
              </div>
            </Group>

            <Group title="Line items">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[340px] table-fixed text-sm">
                  <thead>
                    <tr className="text-left text-xs text-muted-foreground">
                      <th className="w-[44%] px-1 pb-1.5 font-medium">Description</th>
                      <th className="px-1 pb-1.5 text-right font-medium">Qty</th>
                      <th className="px-1 pb-1.5 text-right font-medium">Unit price</th>
                      <th className="px-1 pb-1.5 text-right font-medium">Amount</th>
                      <th className="w-8" />
                    </tr>
                  </thead>
                  <tbody>
                    {doc.items.map((it, n) => (
                      <tr key={n} className={cn(flagged.has(`items[${n}]`) && "bg-warn-soft")}>
                        {(["description", "quantity", "unit_price", "amount"] as const).map((k) => (
                          <td key={k} className="p-0.5">
                            <input
                              aria-label={`Line ${n + 1} ${k.replace("_", " ")}`}
                              inputMode={k === "description" ? undefined : "decimal"}
                              className={cn(inputClass, "h-8 px-2", k !== "description" && "text-right tabular-nums")}
                              value={it[k] ?? ""}
                              onChange={(e) => editItem(n, { [k]: blank(e.target.value) })}
                            />
                          </td>
                        ))}
                        <td className="p-0.5 text-center">
                          <button
                            type="button"
                            aria-label={`Remove line ${n + 1}`}
                            className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary"
                            onClick={() => { setDoc((d) => d && { ...d, items: d.items.filter((_, i) => i !== n) }); setDirty(true); }}
                          >
                            <X className="size-4" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[13px] text-muted-foreground">
                <button type="button" className="py-1 font-semibold text-primary" onClick={() => { setDoc((d) => d && { ...d, items: [...d.items, EMPTY_ITEM] }); setDirty(true); }}>
                  + Add line
                </button>
                <span className="tabular-nums">
                  Lines total {itemsTotal.toFixed(2)}
                  {doc.subtotal !== null && !isNaN(Number(doc.subtotal)) && <> · Subtotal {Number(doc.subtotal).toFixed(2)}</>}
                </span>
              </div>
            </Group>

            <Group title="Amounts">
              <div className="grid gap-x-4 gap-y-3.5 sm:grid-cols-2">
                <Text label="Subtotal" id="subtotal" doc={doc} edit={edit} flagged={flagged} numeric />
                <Text label="Discount" id="discount" doc={doc} edit={edit} flagged={flagged} numeric />
                <Text label="Tax" id="tax" doc={doc} edit={edit} flagged={flagged} numeric />
                <Text label="Service charge" id="service_charge" doc={doc} edit={edit} flagged={flagged} numeric />
                <div className="sm:col-span-2">
                  <Text label="Total" id="total" doc={doc} edit={edit} flagged={flagged} numeric />
                </div>
              </div>
            </Group>
          </form>
        )}

        {doc && (
          <Panel className="p-4 lg:col-span-2 xl:col-span-1 xl:sticky xl:top-5">
            <h2 className="mb-2.5 flex items-center justify-between text-sm font-semibold">
              Checks
              {checks.length > 0 && !checkError && (
                <span className="rounded-full bg-warn-soft px-2 py-0.5 text-xs font-medium text-warn">
                  {checks.length} to fix
                </span>
              )}
            </h2>
            {checkError && (
              <p role="alert" className="mb-3 rounded-md bg-warn-soft p-2.5 text-sm text-warn">
                Checks could not run: {checkError}
              </p>
            )}
            {suggestion && (
              <div className="mb-3 rounded-md border border-primary/30 bg-primary/5 p-3 text-sm">
                <p className="font-medium">Suggested fix</p>
                <p className="mt-0.5 text-xs text-muted-foreground">{suggestion.message}. Compare with the photo before applying.</p>
                {suggestion.changes.length <= 3 && (
                  <ul className="mt-1.5 text-xs">
                    {suggestion.changes.map((c) => (
                      <li key={c.field}>{fieldLabel(c.field)}: <s>{c.from}</s> → <b>{c.to}</b></li>
                    ))}
                  </ul>
                )}
                <Button size="sm" className="mt-2" onClick={() => applySuggestion(suggestion)}>Apply</Button>
              </div>
            )}
            <ul className={cn("divide-y text-sm", checkError && "hidden")}>
              {CHECK_GROUPS.map(([label, names]) => {
                const issue = checks.find((c) => names.includes(c.check));
                return (
                  <li key={label} className={cn("flex gap-2 py-1.5", issue && "font-medium text-warn")}>
                    <span className={cn("w-4 text-center", !issue && "text-ok")} aria-label={issue ? "Needs attention" : "Passed"}>
                      {issue ? "!" : "✓"}
                    </span>
                    <span>
                      {label}
                      {issue && (
                        <span className="block text-xs font-normal">
                          {issue.message}
                          {issue.duplicate_of && (
                            <> · <Link href={`/app/documents/${issue.duplicate_of}`} className="text-primary underline">Open it</Link></>
                          )}
                        </span>
                      )}
                    </span>
                  </li>
                );
              })}
              {dateChoice && (
                <li className={cn("flex gap-2 py-1.5", !order && "font-medium text-warn")}>
                  <span className={cn("w-4 text-center", order && "text-ok")}>{order ? "✓" : "!"}</span>
                  Date format {order ? "confirmed" : "to confirm"}
                </li>
              )}
            </ul>
          </Panel>
        )}
      </div>

      <Dialog open={confirm !== null} onOpenChange={(o) => !o && setConfirm(null)}>
        <DialogContent>
          {confirm === "save" && (
            <>
              <DialogHeader>
                <DialogTitle>{otherFailing.length} {otherFailing.length === 1 ? "check still fails" : "checks still fail"}</DialogTitle>
                <DialogDescription>{otherFailing.map((c) => c.message).join(". ")}. Save anyway?</DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button variant="outline" onClick={() => setConfirm(null)}>Keep editing</Button>
                <Button onClick={save}>Save anyway</Button>
              </DialogFooter>
            </>
          )}
          {confirm === "read" && (
            <>
              <DialogHeader>
                <DialogTitle>Read the document again?</DialogTitle>
                <DialogDescription>Your unsaved edits will be replaced by a new reading.</DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button variant="outline" onClick={() => setConfirm(null)}>Cancel</Button>
                <Button onClick={readAgain}>Read again</Button>
              </DialogFooter>
            </>
          )}
          {confirm === "delete" && (
            <>
              <DialogHeader>
                <DialogTitle>Delete this document?</DialogTitle>
                <DialogDescription>The file and its data are removed for good.</DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button variant="outline" onClick={() => setConfirm(null)}>Cancel</Button>
                <Button variant="destructive" onClick={remove}>Delete</Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

const inputClass =
  "h-9 w-full rounded-md border border-input bg-card px-2.5 text-sm tabular-nums outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:bg-secondary disabled:text-muted-foreground placeholder:text-muted-foreground";
const flagClass = "border-warn-line ring-1 ring-warn-line";

const ITEM_FIELD = /^items\[(\d+)\]\.(\w+)$/;

// "items[2].amount" -> "Line 3 amount", "service_charge" -> "Service charge"
function fieldLabel(field: string) {
  const m = field.match(ITEM_FIELD);
  const name = (m ? m[2] : field).replace("_", " ").replace("unit price", "price");
  return m ? `Line ${Number(m[1]) + 1} ${name}` : name[0].toUpperCase() + name.slice(1);
}

function Panel({ className, children }: { className?: string; children: React.ReactNode }) {
  return <section className={cn("rounded-xl border bg-card shadow-xs", className)}>{children}</section>;
}

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border-b py-5 last:border-b-0">
      <h2 className="mb-3.5 text-sm font-semibold">{title}</h2>
      {children}
    </div>
  );
}

function FieldBox({ label, id, children }: { label: string; id: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1.5">
      <label htmlFor={id} className="text-[13px] font-medium text-foreground/80">{label}</label>
      {children}
    </div>
  );
}

type TextKey = "vendor" | "branch" | "buyer" | "doc_number" | "currency" | "subtotal" | "discount" | "tax" | "service_charge" | "total";

function Text({ label, id, doc, edit, flagged, numeric, list }: {
  label: string; id: TextKey; doc: Doc; edit: (p: Partial<Doc>) => void; flagged: Set<string>; numeric?: boolean; list?: string;
}) {
  return (
    <FieldBox label={label} id={id}>
      <input
        id={id}
        list={list}
        inputMode={numeric ? "decimal" : undefined}
        placeholder="Not on document"
        className={cn(inputClass, flagged.has(id) && flagClass)}
        value={doc[id] ?? ""}
        onChange={(e) => edit({ [id]: blank(e.target.value) })}
      />
    </FieldBox>
  );
}

function Viewer({ id, mime, fileName, onReadAgain, onDelete }: {
  id: string; mime: string; fileName: string; onReadAgain?: () => void; onDelete: () => void;
}) {
  const [pages, setPages] = useState(1);
  const [page, setPage] = useState(0);
  const [src, setSrc] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [turn, setTurn] = useState(0);

  useEffect(() => {
    if (mime === "application/pdf") getJSON<{ pages: number }>(`/documents/${id}/pages`).then((r) => setPages(r.pages)).catch(() => {});
  }, [id, mime]);

  // images need the access token, so they are fetched and shown from a blob URL
  useEffect(() => {
    let url: string | null = null;
    let gone = false; // another page was chosen meanwhile: this image must not replace it
    api(`/documents/${id}/pages/${page}`)
      .then((r) => r.blob())
      .then((b) => {
        if (!gone) setSrc((url = URL.createObjectURL(b)));
      })
      .catch(() => !gone && setSrc(null));
    return () => {
      gone = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [id, page]);

  const label = useMemo(() => (pages > 1 ? `${fileName} · page ${page + 1} of ${pages}` : fileName), [fileName, page, pages]);
  const tool = "grid size-8 place-items-center rounded-md border border-input bg-card hover:bg-secondary disabled:opacity-40";

  return (
    <section aria-label="Original document" className="overflow-hidden rounded-xl border bg-card shadow-xs xl:sticky xl:top-5">
      <div className="flex items-center justify-between gap-2 border-b px-3 py-2 text-[13px] text-muted-foreground">
        <span className="truncate">{label}</span>
        <span className="flex shrink-0 gap-1">
          {pages > 1 && (
            <>
              <button className={tool} aria-label="Previous page" disabled={page === 0} onClick={() => setPage(page - 1)}><ArrowLeft className="size-4" /></button>
              <button className={tool} aria-label="Next page" disabled={page === pages - 1} onClick={() => setPage(page + 1)}><ArrowRight className="size-4" /></button>
            </>
          )}
          <button className={tool} aria-label="Zoom out" disabled={zoom <= 1} onClick={() => setZoom(zoom - 0.5)}><ZoomOut className="size-4" /></button>
          <button className={tool} aria-label="Zoom in" disabled={zoom >= 3} onClick={() => setZoom(zoom + 0.5)}><ZoomIn className="size-4" /></button>
          <button className={tool} aria-label="Rotate" onClick={() => setTurn((turn + 90) % 360)}><RotateCw className="size-4" /></button>
          {onReadAgain && <button className="h-8 rounded-md border border-input px-2.5 font-medium text-foreground hover:bg-secondary" onClick={onReadAgain}>Read again</button>}
          <button className={tool} aria-label="Delete document" onClick={onDelete}><Trash2 className="size-4" /></button>
        </span>
      </div>
      <div className="h-[460px] overflow-auto bg-[#F1F3F6] xl:h-[calc(100vh-140px)]">
        {src ? (
          // eslint-disable-next-line @next/next/no-img-element -- blob URL of a private file; next/image can't optimise it
          <img
            src={src}
            alt={`Original: ${fileName}`}
            className="mx-auto max-w-none object-contain transition-transform"
            // zoom by size, not scale(): a scaled image overflows to the left, where it can't be scrolled to
            style={{ width: `${zoom * 100}%`, height: zoom > 1 ? "auto" : "100%", transform: `rotate(${turn}deg)` }}
          />
        ) : (
          <p className="p-6 text-sm text-muted-foreground">Loading the original…</p>
        )}
      </div>
    </section>
  );
}
