"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { getJSON, type DocumentRow } from "@/lib/api";

// The review queue: every document waiting for review, oldest first. Any of them can be opened, so one hard
// document never blocks the rest.
export default function ReviewQueue() {
  const [rows, setRows] = useState<DocumentRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getJSON<DocumentRow[]>("/documents?status=needs_review&oldest=true&limit=200")
      .then(setRows)
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <p className="text-bad">{error}</p>;
  if (!rows) return <p className="text-muted-foreground">Loading…</p>;
  if (rows.length === 0)
    return (
      <div className="mx-auto mt-16 max-w-md text-center">
        <h1 className="text-xl font-semibold">Nothing to review</h1>
        <p className="mt-1.5 text-muted-foreground">Every document passed its checks or has been reviewed.</p>
        <Button asChild className="mt-5"><Link href="/app/upload">Upload documents</Link></Button>
      </div>
    );
  return (
    <div className="max-w-3xl">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Review</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {rows.length} {rows.length === 1 ? "document needs" : "documents need"} a look. Open any of them.
          </p>
        </div>
        <Button asChild><Link href={`/app/documents/${rows[0].id}`}>Start with the oldest</Link></Button>
      </div>
      <ul className="divide-y rounded-xl border bg-card shadow-xs">
        {rows.map((r) => (
          <li key={r.id}>
            <Link href={`/app/documents/${r.id}`} className="flex items-center justify-between gap-4 px-4 py-3 hover:bg-secondary/60">
              <span className="min-w-0">
                <span className="block truncate font-medium text-primary">{r.vendor ?? "Unknown vendor"}</span>
                <span className="block truncate text-xs text-muted-foreground">{r.file_name}</span>
              </span>
              <span className="shrink-0 text-sm tabular-nums text-muted-foreground">{r.issue_date ?? ""}</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
