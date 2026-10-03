"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Download, Search, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { StatusBadge } from "@/components/status-badge";
import { download, getJSON, money, sendJSON, type DocumentRow } from "@/lib/api";

const PAGE = 50;
const STATUSES = [
  ["", "All statuses"],
  ["needs_review", "Needs review"],
  ["passed", "Passed"],
  ["reviewed", "Reviewed"],
  ["processing", "Processing"],
  ["failed", "Failed"],
];

export default function DocumentsPage() {
  const [rows, setRows] = useState<DocumentRow[] | null>(null);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [more, setMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const filters = useRef(0); // bumped when the filters change: answers for older filters are dropped

  function query(offset: number) {
    const p = new URLSearchParams({ limit: String(PAGE), offset: String(offset) });
    if (q.trim()) p.set("q", q.trim());
    if (status) p.set("status", status);
    return getJSON<DocumentRow[]>(`/documents?${p}`);
  }

  useEffect(() => {
    const current = ++filters.current;
    const timer = setTimeout(
      () =>
        query(0)
          .then((r) => {
            if (current !== filters.current) return;
            setError(null);
            setRows(r);
            setSelected(new Set()); // a new list: nothing hidden stays selected
            setMore(r.length === PAGE);
          })
          .catch((e) => current === filters.current && setError(e.message)),
      250,
    );
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- re-query only when the filters change
  }, [q, status]);

  async function exportAs(format: "csv" | "xlsx" | "quickbooks") {
    try {
      const res = await download(`/export?format=${format}`, `documents.${format === "xlsx" ? "xlsx" : "csv"}`);
      const skipped = Number(res.headers.get("X-Skipped") ?? 0);
      if (skipped) toast.info(`${skipped} document${skipped > 1 ? "s" : ""} without a date or total left out.`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Export failed.");
    }
  }

  // one request per document (the same delete as the review page); the ones that fail stay listed
  async function deleteSelected() {
    setDeleting(true);
    const gone: number[] = [];
    for (const id of selected) {
      try {
        await sendJSON("DELETE", `/documents/${id}`);
        gone.push(id);
      } catch {}
    }
    setRows((prev) => prev && prev.filter((r) => !gone.includes(r.id)));
    setSelected((prev) => new Set([...prev].filter((id) => !gone.includes(id))));
    setDeleting(false);
    setConfirmDelete(false);
    if (gone.length === selected.size) toast.success(`${gone.length} document${gone.length > 1 ? "s" : ""} deleted`);
    else toast.error(`${gone.length} deleted, ${selected.size - gone.length} could not be deleted. Try again.`);
  }

  function toggle(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (!next.delete(id)) next.add(id);
      return next;
    });
  }

  const filtered = q.trim() !== "" || status !== "";
  const allSelected = !!rows?.length && rows.every((r) => selected.has(r.id));

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Documents</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">Everything you have uploaded, newest first</p>
        </div>
        <div className="flex gap-2">
        {selected.size > 0 && (
          <Button variant="destructive" className="h-9" onClick={() => setConfirmDelete(true)}>
            <Trash2 /> Delete {selected.size} selected
          </Button>
        )}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" className="h-9"><Download /> Export</Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onSelect={() => exportAs("xlsx")}>Excel (.xlsx)</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => exportAs("csv")}>CSV</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => exportAs("quickbooks")}>QuickBooks bills (.csv)</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
        </div>
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        <label className="relative min-w-60 flex-1">
          <span className="sr-only">Search by vendor or file name</span>
          <Search className="pointer-events-none absolute top-2.5 left-2.5 size-4 text-muted-foreground" aria-hidden />
          <input
            className="h-9 w-full rounded-md border border-input bg-card pr-3 pl-8 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
            placeholder="Search vendor or file name"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </label>
        <select
          aria-label="Status"
          className="h-9 rounded-md border border-input bg-card px-2.5 text-sm"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          {STATUSES.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
        </select>
      </div>

      {error && <p className="text-bad">{error}</p>}
      {!rows && !error && <p className="text-muted-foreground">Loading…</p>}
      {rows?.length === 0 && (
        <div className="rounded-xl border bg-card px-6 py-14 text-center shadow-xs">
          <p className="font-medium">{filtered ? "No documents match these filters." : "No documents yet."}</p>
          {!filtered && <Button asChild className="mt-4"><Link href="/app/upload">Upload documents</Link></Button>}
        </div>
      )}
      {rows && rows.length > 0 && (
        <div className="overflow-x-auto rounded-xl border bg-card shadow-xs">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="border-b text-left text-xs text-muted-foreground">
                <th className="w-10 py-2.5 pl-4">
                  <input
                    type="checkbox"
                    aria-label="Select all"
                    className="size-4 align-middle"
                    checked={allSelected}
                    disabled={deleting}
                    onChange={() => setSelected(allSelected ? new Set() : new Set(rows.map((r) => r.id)))}
                  />
                </th>
                <th className="px-4 py-2.5 font-medium">Vendor</th>
                <th className="px-4 py-2.5 font-medium">Date</th>
                <th className="px-4 py-2.5 text-right font-medium">Total</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
                <th className="px-4 py-2.5 font-medium">File</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {rows.map((r) => (
                <tr key={r.id} className="hover:bg-secondary/60">
                  <td className="w-10 py-2.5 pl-4">
                    <input
                      type="checkbox"
                      aria-label={`Select ${r.vendor ?? r.file_name}`}
                      className="size-4 align-middle"
                      checked={selected.has(r.id)}
                      disabled={deleting}
                      onChange={() => toggle(r.id)}
                    />
                  </td>
                  <td className="px-4 py-2.5">
                    <Link href={`/app/documents/${r.id}`} className="font-medium text-primary hover:underline">
                      {r.vendor ?? (r.status === "processing" ? "Being read" : "Unknown vendor")}
                    </Link>
                  </td>
                  <td className="px-4 py-2.5 tabular-nums">{r.issue_date ?? "–"}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums">{money(r.total, r.currency)}</td>
                  <td className="px-4 py-2.5"><StatusBadge status={r.status} /></td>
                  <td className="max-w-48 truncate px-4 py-2.5 text-muted-foreground" title={r.file_name}>{r.file_name}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {more && rows && (
        <div className="mt-4 text-center">
          <Button
            variant="outline"
            onClick={() => {
              const current = filters.current;
              query(rows.length)
                .then((r) => {
                  if (current !== filters.current) return;
                  setRows((prev) => [...(prev ?? []), ...r]);
                  setMore(r.length === PAGE);
                })
                .catch((e) => toast.error(e.message));
            }}
          >
            Load more
          </Button>
        </div>
      )}
      <Dialog open={confirmDelete} onOpenChange={(o) => !o && !deleting && setConfirmDelete(false)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete {selected.size} document{selected.size > 1 ? "s" : ""}?</DialogTitle>
            <DialogDescription>The files and their fields are removed. This can&apos;t be undone.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" disabled={deleting} onClick={() => setConfirmDelete(false)}>Cancel</Button>
            <Button variant="destructive" disabled={deleting} onClick={deleteSelected}>{deleting ? "Deleting…" : "Delete"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
