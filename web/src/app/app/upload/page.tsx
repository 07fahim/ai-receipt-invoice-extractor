"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { FileText, Upload } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/status-badge";
import { api, getJSON, money, sendJSON, type DocumentDetail, type Status } from "@/lib/api";
import { cn } from "@/lib/utils";

type Entry = {
  key: string;
  file_name: string;
  preview?: string; // local picture of the file, shown while and after it is read
  uploading?: boolean;
  id?: number;
  status?: Status;
  error?: string;
  vendor?: string | null;
  total?: string | null;
  currency?: string | null;
};
type Usage = { used: number; limit: number };

const ACCEPT = ".jpg,.jpeg,.png,.webp,.heic,.heif,.pdf";
const PREVIEWABLE = ["image/jpeg", "image/png", "image/webp"]; // browsers cannot show HEIC; PDFs get an icon

// Public-domain (CC0) US receipts and our own synthetic Dhaka bill, so visitors can try the app without their own files.
const SAMPLES = [
  { file: "grand-lux-cafe.jpg", label: "US restaurant", note: "Passes all checks" },
  { file: "taco-bell.jpg", label: "US fast food", note: "Has an unclear date" },
  { file: "dhaka-restaurant.png", label: "Dhaka restaurant", note: "With service charge and VAT" },
];

export default function UploadPage() {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [usage, setUsage] = useState<Usage | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const refreshUsage = useCallback(() => {
    getJSON<Usage>("/usage").then(setUsage).catch(() => {});
  }, []);
  useEffect(refreshUsage, [refreshUsage]);
  const left = usage ? Math.max(usage.limit - usage.used, 0) : null;

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

  const send = useCallback(async (files: File[]) => {
    if (!files.length || busy) return;
    if (files.length > 20) {
      toast.error("Upload up to 20 files at a time.");
      return;
    }
    setBusy(true);
    // the rows appear at once; each is filled in when the server answers (one answer per file, in order)
    const stamp = Date.now();
    const rows: Entry[] = files.map((f, i) => ({
      key: `${stamp}-${i}`,
      file_name: f.name,
      preview: PREVIEWABLE.includes(f.type) ? URL.createObjectURL(f) : undefined,
      uploading: true,
    }));
    setEntries((list) => [...rows, ...list]);
    const update = (fill: (row: Entry, i: number) => Entry) =>
      setEntries((list) => list.map((e) => {
        const i = rows.findIndex((r) => r.key === e.key);
        return i === -1 ? e : { ...fill(e, i), uploading: false };
      }));
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    try {
      const created: { id?: number; status?: Status; error?: string }[] = await (
        await api("/documents", { method: "POST", body: form })
      ).json();
      update((e, i) => ({ ...e, ...created[i] }));
    } catch (err) {
      const message = err instanceof Error ? err.message : "Upload failed.";
      update((e) => ({ ...e, error: message }));
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
      refreshUsage();
    }
  }, [busy, refreshUsage]);

  // Paste a screenshot or a copied image (Ctrl+V) anywhere on the page.
  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      const files = [...(e.clipboardData?.files ?? [])];
      if (files.length) send(files.map((f, i) => (f.name === "image.png" ? new File([f], `pasted-${Date.now()}-${i}.png`, { type: f.type }) : f)));
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [send]);

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
    } finally {
      refreshUsage();
    }
  }

  const count = (s: Status) => entries.filter((e) => e.status === s).length;
  const reading = entries.filter((e) => e.uploading || e.status === "processing").length;
  const flagged = count("needs_review");
  const summary = [
    [count("passed") + count("reviewed"), "done"],
    [flagged, "needs review"],
    [reading, "reading"],
    [count("failed") + entries.filter((e) => e.error && !e.id).length, "failed"],
  ]
    .filter(([n]) => n)
    .map(([n, label]) => `${n} ${label}`)
    .join(" · ");
  const limitReached = left === 0;

  return (
    <div className="mx-auto max-w-5xl">
      <h1 className="text-2xl font-semibold tracking-tight">Upload</h1>
      <p className="mt-0.5 text-sm text-muted-foreground">
        Up to 20 files at a time. Google&apos;s Gemini AI reads them. Please use sample receipts.{" "}
        <Link href="/privacy" className="underline">Privacy</Link>
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
        <span className="mt-1 text-sm text-muted-foreground">JPG, PNG, WebP, HEIC or PDF · up to 10 MB each</span>
        <span className="mt-0.5 hidden text-sm text-muted-foreground pointer-fine:inline">or paste an image with Ctrl+V</span>
        <Button asChild className="mt-4 h-10 px-4" disabled={busy}>
          <span>{busy ? "Uploading…" : "Choose files"}</span>
        </Button>
        <input ref={input} type="file" multiple accept={ACCEPT} className="sr-only" onChange={(e) => send([...(e.target.files ?? [])])} />
      </label>

      {usage && (
        <p className={cn("mt-2.5 text-sm", limitReached ? "font-medium text-bad" : "text-muted-foreground")} aria-live="polite">
          {limitReached
            ? "No reads left today. Try again tomorrow."
            : `${left} of ${usage.limit} reads left today.`}
        </p>
      )}

      {entries.length > 0 && (
        <section aria-labelledby="batch" className="mt-6 overflow-hidden rounded-xl border bg-card shadow-xs">
          <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b px-5 py-3.5">
            <div>
              <h2 id="batch" className="font-semibold">This batch</h2>
              <p className="text-sm text-muted-foreground" aria-live="polite">{summary}</p>
            </div>
            <div className="flex gap-2">
              {flagged > 0 && (
                <Button asChild size="sm"><Link href="/app/review">Review {flagged} flagged</Link></Button>
              )}
              <Button asChild size="sm" variant="outline"><Link href="/app/documents">All documents</Link></Button>
            </div>
          </div>
          <ul className="divide-y">
            {entries.map((e) => {
              const isReading = e.uploading || e.status === "processing";
              return (
                <li key={e.key} className="grid grid-cols-[40px_1fr] items-center gap-x-3.5 gap-y-2 px-5 py-3 sm:grid-cols-[40px_1fr_auto_88px]">
                  <span
                    className="grid h-12 w-10 place-items-center overflow-hidden rounded-md border bg-secondary bg-cover bg-top text-[10px] font-semibold text-muted-foreground"
                    style={e.preview ? { backgroundImage: `url(${e.preview})` } : undefined}
                    aria-hidden
                  >
                    {!e.preview && (e.file_name.toLowerCase().endsWith(".pdf") ? <FileText className="size-4" /> : e.file_name.split(".").pop()?.toUpperCase().slice(0, 4))}
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate font-medium">{e.file_name}</span>
                    {isReading && !e.error ? (
                      <span className="mt-1.5 block h-1 w-44 max-w-full overflow-hidden rounded-full bg-secondary">
                        <span className="block h-full w-1/2 animate-pulse rounded-full bg-primary" />
                      </span>
                    ) : (
                      <span className={cn("block truncate text-[13px] first-letter:uppercase", e.error ? "text-bad" : "text-muted-foreground")}>
                        {e.error ?? [e.vendor, e.total && money(e.total, e.currency)].filter(Boolean).join(" · ")}
                      </span>
                    )}
                  </span>
                  <span className="col-start-2 sm:col-start-auto">
                    {e.uploading ? <StatusBadge status="processing" /> : e.status ? <StatusBadge status={e.status} /> : <StatusBadge status="failed" />}
                  </span>
                  <span className="col-start-2 text-sm font-medium sm:col-start-auto sm:text-right">
                    {e.status === "needs_review" && <Link className="text-primary hover:underline" href={`/app/documents/${e.id}`}>Review</Link>}
                    {(e.status === "passed" || e.status === "reviewed") && <Link className="text-primary hover:underline" href={`/app/documents/${e.id}`}>Open</Link>}
                    {e.status === "failed" && e.id && (
                      <button className="text-primary hover:underline" onClick={() => readAgain(e.id!)}>Read again</button>
                    )}
                  </span>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      <section aria-labelledby="samples" className="mt-8">
        <h2 id="samples" className="text-sm font-semibold">Or try a sample</h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          {SAMPLES.map((s) => (
            <button
              key={s.file}
              type="button"
              disabled={busy || limitReached}
              onClick={() => trySample(s.file)}
              className="flex items-center gap-3 rounded-xl border bg-card p-3 text-left shadow-xs transition-colors hover:border-primary hover:bg-[#F8FAFF] focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50"
            >
              {/* eslint-disable-next-line @next/next/no-img-element -- tiny static thumbnails */}
              <img src={`/samples/${s.file}`} alt="" className="h-14 w-11 shrink-0 rounded-md border object-cover object-top" />
              <span className="min-w-0">
                <span className="block text-sm font-medium">{s.label}</span>
                <span className="block text-[13px] text-muted-foreground">{s.note}</span>
              </span>
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
