"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Fragment, useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  AlertTriangle, CalendarClock, Check, FileText, History, MessageCircle, Minimize2, PanelRight, Plus,
  SendHorizontal, Sparkles, Store, Trash2, Wallet, X,
} from "lucide-react";
import { api, getJSON, sendJSON } from "@/lib/api";

type Msg = { role: "user" | "assistant"; content: string; steps?: string[] };
type ChatRow = { id: number; title: string; updated_at: string };
type Mode = "closed" | "small" | "docked";
const MODE = "assistant-mode";
const SIZE = "assistant-size";
const CHAT = "assistant-chat"; // the open chat, reopened after a page reload

const DOC_ASKS = [
  { q: "Why is this flagged?", icon: AlertTriangle },
  { q: "What is on this document?", icon: FileText },
];
const ALL_ASKS = [
  { q: "How much did I spend last month?", icon: Wallet },
  { q: "Which bills are due this week?", icon: CalendarClock },
  { q: "Who are my top vendors?", icon: Store },
];
// "Aarong: 6,200 BDT", "Starbucks 5.50 USD", "Total $105.50", "Rice ৳450",
// "Label: 966.98" (bare number after a colon), with an optional "(1 document)" tail.
const AMOUNT = /^(.+?)[\s:,-]+((?:[$৳€£₹]\s?[\d,]+(?:\.\d+)?)|(?:[\d,]+(?:\.\d+)?\s?[A-Z]{3})|(?<=:\s*)[\d,]+(?:\.\d+)?)(?:\s*(\(\d+\s+\w+\)))?$/;

/** **bold** becomes <strong>, "#14" becomes a link to that document. */
function inline(text: string) {
  return text.split(/(\*\*[^*]+\*\*|#\d+)/g).map((part, i) =>
    /^#\d+$/.test(part) ? (
      <Link key={i} href={`/app/documents/${part.slice(1)}`}
        className="rounded bg-primary/10 px-1.5 text-xs font-semibold text-primary hover:bg-primary/20">{part}</Link>
    ) : /^\*\*[^*]+\*\*$/.test(part) ? (
      <strong key={i}>{part.slice(2, -2)}</strong>
    ) : (
      <Fragment key={i}>{part}</Fragment>
    ),
  );
}

/** Plain model text: "- " or "• " lines become a list (amounts right-aligned), the rest paragraphs. */
function formatAnswer(text: string) {
  const blocks: { list: boolean; lines: string[] }[] = [];
  let prev = "";
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    const item = /^(-|•) /.test(line);
    if (!line) prev = "";
    else if (item && prev === "list") blocks[blocks.length - 1].lines.push(line.slice(2));
    else if (!item && prev === "p") blocks[blocks.length - 1].lines.push(line);
    else blocks.push({ list: item, lines: [item ? line.slice(2) : line] });
    if (line) prev = item ? "list" : "p";
  }
  return blocks.map((b, i) =>
    b.list ? (
      <ul key={i} className="divide-y divide-dashed">
        {b.lines.map((l, j) => {
          const m = l.match(AMOUNT);
          return (
            <li key={j} className="flex gap-3 py-1">
              {m ? (
                <>
                  <span className="min-w-0 flex-1">
                    {inline(m[1].replace(/[,;]\s*$/, ""))}
                    {m[3] && <span className="ml-1 text-xs text-muted-foreground">{m[3]}</span>}
                  </span>
                  <span className="font-semibold tabular-nums">{m[2]}</span>
                </>
              ) : inline(l)}
            </li>
          );
        })}
      </ul>
    ) : (
      <p key={i}>{b.lines.map((l, j) => <Fragment key={j}>{j > 0 && <br />}{inline(l)}</Fragment>)}</p>
    ),
  );
}

function Avatar({ big = false }: { big?: boolean }) {
  return (
    <span className={`grid flex-none place-items-center bg-gradient-to-br from-primary to-violet-600 text-white ${
      big ? "size-9 rounded-xl" : "size-6 rounded-lg"}`}>
      <Sparkles className={big ? "size-4" : "size-3.5"} />
    </span>
  );
}

export function AssistantPanel() {
  const path = usePathname();
  const [mode, setMode] = useState<Mode>("closed");
  const [chatId, setChatId] = useState<number | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [chats, setChats] = useState<ChatRow[] | null>(null); // null: the list is hidden
  const [confirmAll, setConfirmAll] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const docId = path.match(/^\/app\/documents\/(\d+)/)?.[1];

  useLayoutEffect(() => {
    // localStorage doesn't exist during SSR, so the mode can only be restored after mount
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMode((localStorage.getItem(MODE) as Mode | null) ?? "closed");
    const saved = Number(localStorage.getItem(CHAT));
    if (saved)
      getJSON<{ messages: Msg[] }>(`/assistant/chats/${saved}`)
        .then((c) => { setChatId(saved); setMsgs(c.messages); })
        .catch(() => localStorage.removeItem(CHAT)); // deleted elsewhere, or signed out
  }, []);
  useEffect(() => {
    document.documentElement.dataset.assistant = mode; // docked: globals.css narrows the page
    localStorage.setItem(MODE, mode);
    if (mode !== "closed") localStorage.setItem(SIZE, mode);
    return () => { delete document.documentElement.dataset.assistant; };
  }, [mode]);
  // braces: newer browsers return a Promise from scrollIntoView, and an effect may only return a cleanup
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [msgs, busy]);

  function keep(id: number | null) {
    setChatId(id);
    if (id) localStorage.setItem(CHAT, String(id));
    else localStorage.removeItem(CHAT);
  }

  const open = () => setMode((localStorage.getItem(SIZE) as Mode | null) ?? "small");

  function newChat() {
    keep(null);
    setMsgs([]);
    setChats(null);
    setError(null);
    setConfirmAll(false);
  }

  async function run(f: () => Promise<void>) {
    try {
      setError(null);
      await f();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    }
  }

  async function ask(raw: string) {
    const q = raw.trim();
    if (!q || busy) return;
    setBusy(true);
    setError(null);
    setMsgs((m) => [...m, { role: "user", content: q }]);
    try {
      const r = await sendJSON<{ chat_id: number; reply: string; steps: string[] }>("POST", "/assistant/messages", {
        chat_id: chatId, text: q, page: path, document_id: docId ? Number(docId) : null,
      });
      keep(r.chat_id);
      setText("");
      setMsgs((m) => [...m, { role: "assistant", content: r.reply, steps: r.steps }]);
    } catch (err) {
      setMsgs((m) => m.slice(0, -1));
      setText((t) => (t.trim() ? t : q)); // the question stays in the box to send again
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  function send(e: { preventDefault(): void }) {
    e.preventDefault();
    ask(text);
  }

  if (mode === "closed")
    return (
      <button
        onClick={open}
        aria-label="Open the assistant"
        className="fixed right-4 bottom-20 z-30 grid size-12 place-items-center rounded-full bg-primary text-primary-foreground shadow-lg md:right-6 md:bottom-6"
      >
        <MessageCircle className="size-5" />
      </button>
    );

  const icon = "grid size-8 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-50";
  const label = "text-[11px] font-semibold tracking-wide text-muted-foreground uppercase";
  const chip = (s: { q: string; icon: typeof Wallet }) => (
    <button key={s.q} disabled={busy} onClick={() => ask(s.q)}
      className="flex w-full items-center gap-2.5 rounded-xl border px-3 py-1.5 text-left hover:border-primary hover:bg-primary/5 disabled:opacity-50">
      <span className="grid size-6 flex-none place-items-center rounded-md bg-primary/10 text-primary"><s.icon className="size-3.5" /></span>
      {s.q}
    </button>
  );
  const title = msgs.find((m) => m.role === "user")?.content ?? "Answers from your documents";

  return (
    <aside
      aria-label="Assistant"
      className={`fixed z-40 flex flex-col bg-card max-md:inset-0 ${
        mode === "small"
          ? "md:right-6 md:bottom-6 md:h-[560px] md:w-[380px] md:overflow-hidden md:rounded-2xl md:border md:shadow-2xl"
          : "md:inset-y-0 md:right-0 md:w-[380px] md:border-l"
      }`}
    >
      <header className="flex items-center gap-1 border-b px-3 py-2">
        <span className="mr-1 grid size-7 flex-none place-items-center rounded-lg bg-gradient-to-br from-primary to-violet-600 text-white">
          <Sparkles className="size-4" />
        </span>
        <div className="min-w-0 flex-1 leading-tight">
          <p className="text-sm font-semibold">Assistant</p>
          <p className="truncate text-xs text-muted-foreground">{title}</p>
        </div>
        <button className={icon} aria-label="Chats" disabled={busy} onClick={() => { setConfirmAll(false); if (chats) setChats(null); else run(async () => setChats(await getJSON<ChatRow[]>("/assistant/chats"))); }}>
          <History className="size-4" />
        </button>
        <button className={icon} aria-label="New chat" disabled={busy} onClick={newChat}><Plus className="size-4" /></button>
        <button className={`${icon} max-md:hidden`} aria-label={mode === "small" ? "Dock to the side" : "Make it small"}
          onClick={() => setMode(mode === "small" ? "docked" : "small")}>
          {mode === "small" ? <PanelRight className="size-4" /> : <Minimize2 className="size-4" />}
        </button>
        <button className={icon} aria-label="Close" onClick={() => setMode("closed")}><X className="size-4" /></button>
      </header>

      {chats ? (
        <div className="flex flex-1 flex-col overflow-y-auto p-2">
          {chats.length === 0 && <p className="p-3 text-sm text-muted-foreground">No chats yet.</p>}
          {chats.map((c) => (
            <div key={c.id} className="group flex items-center gap-1 rounded-lg hover:bg-accent">
              <button className="flex min-w-0 flex-1 items-center gap-2 px-3 py-2 text-left text-sm"
                onClick={() => run(async () => {
                  const chat = await getJSON<{ messages: Msg[] }>(`/assistant/chats/${c.id}`);
                  keep(c.id);
                  setMsgs(chat.messages);
                  setChats(null);
                  setConfirmAll(false);
                })}>
                <span className="min-w-0 flex-1 truncate">{c.title}</span>
                <span className="flex-none text-xs text-muted-foreground">
                  {new Date(c.updated_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                </span>
              </button>
              <button className={`${icon} opacity-0 group-hover:opacity-100 focus-visible:opacity-100 max-md:opacity-100`} aria-label="Delete chat"
                onClick={() => run(async () => {
                  await api(`/assistant/chats/${c.id}`, { method: "DELETE" });
                  if (c.id === chatId) { keep(null); setMsgs([]); }
                  setChats((cs) => cs?.filter((x) => x.id !== c.id) ?? null);
                })}>
                <Trash2 className="size-4" />
              </button>
            </div>
          ))}
          {chats.length > 0 && (
            <button className="mt-auto self-start rounded-md px-3 py-2 text-xs font-medium text-destructive hover:bg-destructive/10"
              onClick={() => run(async () => {
                if (!confirmAll) return setConfirmAll(true);
                await api("/assistant/chats", { method: "DELETE" });
                setConfirmAll(false);
                newChat();
              })}>
              {confirmAll ? "Click again to delete every chat" : "Delete all chats"}
            </button>
          )}
        </div>
      ) : msgs.length === 0 && !busy ? (
        <div className="flex flex-1 flex-col overflow-y-auto p-4 text-sm">
          <div className="my-auto flex flex-col gap-3">
            <div className="flex flex-col items-center gap-1 text-center">
              <Avatar big />
              <h2 className="mt-1 text-base font-semibold">Ask about your documents</h2>
              <p className="text-xs text-muted-foreground">Spending, due bills, or why a receipt was flagged.</p>
            </div>
            <div className="space-y-1.5">
              {docId && <><p className={label}>This document</p>{DOC_ASKS.map(chip)}</>}
              <p className={`${label} ${docId ? "pt-1" : ""}`}>Your documents</p>
              {ALL_ASKS.map(chip)}
            </div>
          </div>
        </div>
      ) : (
        <div className="flex-1 space-y-4 overflow-y-auto p-3 text-sm">
          {msgs.map((m, i) =>
            m.role === "user" ? (
              <p key={i} className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-3 py-2 whitespace-pre-wrap text-primary-foreground">{m.content}</p>
            ) : (
              <div key={i} className="flex gap-2">
                <Avatar />
                <div className="min-w-0 flex-1">
                  {!!m.steps?.length && (
                    <div className="mb-1.5 flex flex-wrap gap-1">
                      {m.steps.map((s, j) => (
                        <span key={j} className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                          <Check className="size-3 text-green-600" />{s}
                        </span>
                      ))}
                    </div>
                  )}
                  <div className="space-y-2 rounded-2xl rounded-tl-sm border bg-muted/40 px-3 py-2 leading-relaxed">{formatAnswer(m.content)}</div>
                </div>
              </div>
            ),
          )}
          {busy && (
            <div className="flex gap-2">
              <Avatar />
              <div className="flex gap-1 rounded-2xl rounded-tl-sm bg-muted/60 px-3 py-2.5">
                <span className="sr-only">Looking it up</span>
                {["", "[animation-delay:150ms]", "[animation-delay:300ms]"].map((d) => (
                  <span key={d} className={`size-1.5 rounded-full bg-muted-foreground/60 motion-safe:animate-bounce ${d}`} />
                ))}
              </div>
            </div>
          )}
          <div ref={end} />
        </div>
      )}

      <div className="border-t p-3">
        {error && <p className="mb-2 rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}
        <form onSubmit={send} className="flex items-end gap-2 rounded-xl border bg-background p-1.5 pl-3 focus-within:ring-2 focus-within:ring-ring">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) send(e); }}
            maxLength={1000}
            rows={1}
            placeholder="Ask about your documents"
            aria-label="Ask about your documents"
            className="max-h-32 min-h-8 flex-1 resize-none bg-transparent py-1.5 text-sm outline-none [field-sizing:content]"
          />
          <button type="submit" disabled={busy || !text.trim()} aria-label="Send"
            className="grid size-8 flex-none place-items-center rounded-lg bg-primary text-primary-foreground disabled:opacity-50">
            <SendHorizontal className="size-4" />
          </button>
        </form>
        {msgs.length === 0 && <p className="mt-1.5 text-center text-[11px] text-muted-foreground">Enter to send. Shift+Enter for a new line.</p>}
      </div>
    </aside>
  );
}
