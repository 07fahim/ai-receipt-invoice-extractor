"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Download, Search } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { StatusBadge } from "@/components/status-badge";
import { download, getJSON, money, type DocumentRow } from "@/lib/api";

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

  function query(offset: number) {
    const p = new URLSearchParams({ limit: String(PAGE), offset: String(offset) });
    if (q.trim()) p.set("q", q.trim());
    if (status) p.set("status", status);
    return getJSON<DocumentRow[]>(`/documents?${p}`);
  }

  useEffect(() => {
    const timer = setTimeout(
      () =>
        query(0)
          .then((r) => {
            setRows(r);
            setMore(r.length === PAGE);
          })
          .catch((e) => setError(e.message)),
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

  const filtered = q.trim() !== "" || status !== "";

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Documents</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">Everything you have uploaded, newest first</p>
        </div>
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
            onClick={() =>
              query(rows.length)
                .then((r) => {
                  setRows([...rows, ...r]);
                  setMore(r.length === PAGE);
                })
                .catch((e) => toast.error(e.message))
            }
          >
            Load more
          </Button>
        </div>
      )}
    </div>
  );
}
