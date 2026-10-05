"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Fragment, useEffect, useLayoutEffect, useRef, useState } from "react";
import { History, MessageCircle, Minimize2, PanelRight, Plus, SendHorizontal, Trash2, X } from "lucide-react";
import { api, getJSON, sendJSON } from "@/lib/api";

type Msg = { role: "user" | "assistant"; content: string; steps?: string[] };
type ChatRow = { id: number; title: string; updated_at: string };
type Mode = "closed" | "small" | "docked";
const MODE = "assistant-mode";
const SIZE = "assistant-size";

/** "#14" in an answer becomes a link to that document. */
function linked(text: string) {
  return text.split(/(#\d+)/g).map((part, i) =>
    /^#\d+$/.test(part) ? (
      <Link key={i} href={`/app/documents/${part.slice(1)}`} className="font-medium text-primary underline">{part}</Link>
    ) : (
      <Fragment key={i}>{part}</Fragment>
    ),
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
  }, []);
  useEffect(() => {
    document.documentElement.dataset.assistant = mode; // docked: globals.css narrows the page
    localStorage.setItem(MODE, mode);
    if (mode !== "closed") localStorage.setItem(SIZE, mode);
    return () => { delete document.documentElement.dataset.assistant; };
  }, [mode]);
  useEffect(() => end.current?.scrollIntoView({ block: "end" }), [msgs, busy]);

  const open = () => setMode((localStorage.getItem(SIZE) as Mode | null) ?? "small");

  function newChat() {
    setChatId(null);
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

  async function send(e: { preventDefault(): void }) {
    e.preventDefault();
    const q = text.trim();
    if (!q || busy) return;
    setBusy(true);
    setError(null);
    setMsgs((m) => [...m, { role: "user", content: q }]);
    try {
      const r = await sendJSON<{ chat_id: number; reply: string; steps: string[] }>("POST", "/assistant/messages", {
        chat_id: chatId, text: q, page: path, document_id: docId ? Number(docId) : null,
      });
      setChatId(r.chat_id);
      setText("");
      setMsgs((m) => [...m, { role: "assistant", content: r.reply, steps: r.steps }]);
    } catch (err) {
      setMsgs((m) => m.slice(0, -1)); // the question stays in the box to send again
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
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
  return (
    <aside
      aria-label="Assistant"
      className={`fixed z-40 flex flex-col bg-card max-md:inset-0 ${
        mode === "small"
          ? "md:right-6 md:bottom-6 md:h-[520px] md:w-[360px] md:rounded-xl md:border md:shadow-xl"
          : "md:inset-y-0 md:right-0 md:w-[380px] md:border-l"
      }`}
    >
      <header className="flex items-center gap-1 border-b px-3 py-2">
        <span className="flex-1 font-semibold">Assistant</span>
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
        <div className="flex-1 overflow-y-auto p-2">
          {chats.length === 0 && <p className="p-3 text-sm text-muted-foreground">No chats yet.</p>}
          {chats.map((c) => (
            <div key={c.id} className="group flex items-center gap-1 rounded-md hover:bg-accent">
              <button className="flex-1 truncate px-3 py-2 text-left text-sm"
                onClick={() => run(async () => {
                  const chat = await getJSON<{ messages: Msg[] }>(`/assistant/chats/${c.id}`);
                  setChatId(c.id);
                  setMsgs(chat.messages);
                  setChats(null);
                  setConfirmAll(false);
                })}>
                {c.title}
              </button>
              <button className={icon} aria-label="Delete chat"
                onClick={() => run(async () => {
                  await api(`/assistant/chats/${c.id}`, { method: "DELETE" });
                  if (c.id === chatId) { setChatId(null); setMsgs([]); }
                  setChats((cs) => cs?.filter((x) => x.id !== c.id) ?? null);
                })}>
                <Trash2 className="size-4" />
              </button>
            </div>
          ))}
          {chats.length > 0 && (
            <button className="mt-2 w-full rounded-md px-3 py-2 text-left text-sm text-destructive hover:bg-accent"
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
      ) : (
        <div className="flex-1 space-y-3 overflow-y-auto p-3 text-sm">
          {msgs.length === 0 && (
            <p className="text-muted-foreground">
              Ask about your documents. For example: &quot;How much did I spend last month?&quot;,
              &quot;Which bills are due this week?&quot; or, on a document, &quot;Why is this flagged?&quot;
            </p>
          )}
          {msgs.map((m, i) =>
            m.role === "user" ? (
              <p key={i} className="ml-auto w-fit max-w-[85%] rounded-xl bg-primary px-3 py-2 text-primary-foreground">{m.content}</p>
            ) : (
              <div key={i} className="max-w-[92%]">
                {m.steps?.map((s, j) => <p key={j} className="mb-1 text-xs text-muted-foreground">{s}</p>)}
                <p className="rounded-xl bg-muted px-3 py-2 whitespace-pre-wrap">{linked(m.content)}</p>
              </div>
            ),
          )}
          {busy && <p className="text-xs text-muted-foreground">Looking it up…</p>}
          <div ref={end} />
        </div>
      )}

      {error && <p className="px-3 pb-1 text-sm text-destructive">{error}</p>}
      <form onSubmit={send} className="flex items-end gap-2 border-t p-2">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) send(e); }}
          maxLength={1000}
          rows={2}
          placeholder="Ask about your documents"
          aria-label="Ask about your documents"
          className="flex-1 resize-none rounded-md border bg-background px-2 py-1.5 text-sm outline-none focus:ring-2 focus:ring-ring"
        />
        <button type="submit" disabled={busy || !text.trim()} aria-label="Send"
          className="grid size-9 place-items-center rounded-md bg-primary text-primary-foreground disabled:opacity-50">
          <SendHorizontal className="size-4" />
        </button>
      </form>
    </aside>
  );
}
