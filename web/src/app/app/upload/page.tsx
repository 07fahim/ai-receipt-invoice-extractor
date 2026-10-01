"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Upload } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/status-badge";
import { api, getJSON, money, sendJSON, type DocumentDetail, type Status } from "@/lib/api";
import { cn } from "@/lib/utils";

type Entry = { key: string; file_name: string; id?: number; status?: Status; error?: string; vendor?: string | null; total?: string | null; currency?: string | null };

const ACCEPT = ".jpg,.jpeg,.png,.webp,.heic,.heif,.pdf";

// Public-domain (CC0) US receipts and our own synthetic Dhaka bill, so visitors can try the app without their own files.
const SAMPLES = [
  { file: "grand-lux-cafe.jpg", label: "US restaurant", note: "passes all checks" },
  { file: "taco-bell.jpg", label: "US fast food", note: "unclear date, goes to review" },
  { file: "dhaka-restaurant.png", label: "Dhaka restaurant", note: "service charge + VAT" },
];

export default function UploadPage() {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  // Poll documents that are still being read, every 2 seconds.
  const pending = entries.filter((e) => e.id && e.status === "processing").map((e) => e.id!);
  const pendingKey = pending.join(",");
  useEffect(() => {
    if (!pendingKey) return;
    const timer = setTimeout(async () => {
      const done = await Promise.all(
        pendingKey.split(",").map((id) => getJSON<DocumentDetail>(`/documents/${id}`).catch(() => null)),
      );
      setEntries((list) =>
        list.map((e) => {
          const d = done.find((x) => x?.id === e.id);
          return d ? { ...e, status: d.status, error: d.error ?? undefined, vendor: d.vendor, total: d.document?.total ?? null, currency: d.currency } : e;
        }),
      );
    }, 2000);
    return () => clearTimeout(timer);
  }, [pendingKey, entries]);

  async function send(files: File[]) {
    if (!files.length || busy) return;
    if (files.length > 20) {
      toast.error("Upload up to 20 files at a time.");
      return;
    }
    setBusy(true);
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    try {
      const created: { id?: number; file_name: string; status?: Status; error?: string }[] = await (
        await api("/documents", { method: "POST", body: form })
      ).json();
      setEntries((list) => [...created.map((c, i) => ({ ...c, key: `${Date.now()}-${i}` })), ...list]);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Upload failed.");
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  async function trySample(name: string) {
    try {
      const blob = await (await fetch(`/samples/${name}`)).blob();
      await send([new File([blob], name, { type: blob.type })]);
    } catch {
      toast.error("Could not load the sample.");
    }
  }

  async function readAgain(id: number) {
    try {
      await sendJSON("POST", `/documents/${id}/retry`);
      setEntries((list) => list.map((e) => (e.id === id ? { ...e, status: "processing", error: undefined } : e)));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not read the file again.");
    }
  }

  const count = (s: Status) => entries.filter((e) => e.status === s).length;
  const summary = [
    [count("passed") + count("reviewed"), "done"],
    [count("needs_review"), "needs review"],
    [count("processing"), "processing"],
    [count("failed") + entries.filter((e) => e.error && !e.id).length, "failed"],
  ]
    .filter(([n]) => n)
    .map(([n, label]) => `${n} ${label}`)
    .join(" · ");

  return (
    <div className="mx-auto max-w-5xl">
      <h1 className="text-2xl font-semibold tracking-tight">Upload</h1>
      <p className="mt-0.5 text-sm text-muted-foreground">
        Receipts and invoices, up to 20 files at a time. Files are read by Google&apos;s Gemini AI, so please use sample documents
        (<Link href="/privacy" className="underline">privacy</Link>).
      </p>

      <label
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          send([...e.dataTransfer.files]);
        }}
        className={cn(
          "mt-5 grid cursor-pointer place-items-center rounded-xl border-2 border-dashed border-[#C7CDD6] bg-card px-6 py-12 text-center transition-colors hover:border-primary hover:bg-[#F8FAFF] focus-within:ring-2 focus-within:ring-ring",
          dragging && "border-primary bg-[#F8FAFF]",
        )}
      >
        <span className="mb-3.5 grid size-12 place-items-center rounded-xl bg-accent text-primary">
          <Upload className="size-6" aria-hidden />
        </span>
        <span className="text-[17px] font-semibold">
          <span className="hidden pointer-fine:inline">Drop files here</span>
          <span className="pointer-fine:hidden">Choose files</span>
        </span>
        <span className="mt-1 mb-4 text-sm text-muted-foreground">JPG, PNG, WebP, HEIC or PDF · up to 10 MB each</span>
        <Button asChild className="h-10 px-4" disabled={busy}>
          <span>{busy ? "Uploading…" : "Choose files"}</span>
        </Button>
        <input ref={input} type="file" multiple accept={ACCEPT} className="sr-only" onChange={(e) => send([...(e.target.files ?? [])])} />
      </label>

      <div className="mt-4 flex flex-wrap items-center gap-2 text-sm">
        <span className="text-muted-foreground">No receipt at hand? Try a sample:</span>
        {SAMPLES.map((s) => (
          <Button key={s.file} variant="outline" size="sm" disabled={busy} title={s.note} onClick={() => trySample(s.file)}>
            {s.label}
          </Button>
        ))}
      </div>

      {entries.length > 0 && (
        <section aria-labelledby="batch" className="mt-6 overflow-hidden rounded-xl border bg-card shadow-xs">
          <div className="flex flex-wrap items-center justify-between gap-1 border-b px-5 py-3.5">
            <h2 id="batch" className="font-semibold">This batch</h2>
            <span className="text-sm text-muted-foreground" aria-live="polite">{summary}</span>
          </div>
          <ul className="divide-y">
            {entries.map((e) => (
              <li key={e.key} className="grid grid-cols-[36px_1fr] items-center gap-x-3.5 gap-y-2 px-5 py-3 sm:grid-cols-[36px_1fr_auto_80px]">
                <span className="grid h-11 w-9 place-items-center rounded-md bg-secondary text-[10px] font-semibold text-muted-foreground">
                  {e.file_name.split(".").pop()?.toUpperCase().slice(0, 4)}
                </span>
                <span className="min-w-0">
                  <span className="block truncate font-medium">{e.file_name}</span>
                  <span className="block truncate text-[13px] text-muted-foreground">
                    {e.error ??
                      (e.status === "processing" ? "Reading…" : [e.vendor, e.total && money(e.total, e.currency)].filter(Boolean).join(" · "))}
                  </span>
                </span>
                <span className="col-start-2 sm:col-start-auto">
                  {e.status ? <StatusBadge status={e.status} /> : <StatusBadge status="failed" />}
                </span>
                <span className="col-start-2 text-sm font-medium sm:col-start-auto sm:text-right">
                  {e.status === "needs_review" && <Link className="text-primary hover:underline" href={`/app/documents/${e.id}`}>Review</Link>}
                  {(e.status === "passed" || e.status === "reviewed") && <Link className="text-primary hover:underline" href={`/app/documents/${e.id}`}>Open</Link>}
                  {e.status === "failed" && e.id && (
                    <button className="text-primary hover:underline" onClick={() => readAgain(e.id!)}>Read again</button>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
