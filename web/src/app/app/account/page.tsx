"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getJSON, sendJSON } from "@/lib/api";
import { createClient } from "@/lib/supabase/client";

export default function AccountPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    createClient().auth.getUser().then(({ data }) => setEmail(data.user?.email ?? ""));
  }, []);

  async function signOut() {
    await createClient().auth.signOut();
    router.replace("/");
    router.refresh();
  }

  async function deleteAccount() {
    setBusy(true);
    try {
      await sendJSON("DELETE", "/account");
      await createClient().auth.signOut({ scope: "local" }); // the account is gone, so only clear this browser's session
      toast.success("Your account and all your documents were deleted.");
      router.replace("/");
      router.refresh();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not delete the account.");
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-2xl font-semibold tracking-tight">Account</h1>

      <section className="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-card px-5 py-4 shadow-xs">
        <div>
          <p className="text-[13px] text-muted-foreground">Signed in as</p>
          <p className="font-medium">{email || "…"}</p>
        </div>
        <Button variant="outline" onClick={signOut}>Log out</Button>
      </section>

      <WebhookCard />

      <section className="mt-5 rounded-xl border border-bad/30 bg-card px-5 py-4 shadow-xs">
        <h2 className="font-semibold">Delete account</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Deletes your account and all your documents. This can&apos;t be undone.
        </p>
        <Button variant="destructive" className="mt-4" onClick={() => setOpen(true)}>Delete my account</Button>
      </section>

      <Dialog open={open} onOpenChange={(o) => { setOpen(o); setTyped(""); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete your account?</DialogTitle>
            <DialogDescription>Type DELETE to confirm. All your documents are removed for good.</DialogDescription>
          </DialogHeader>
          <input
            aria-label="Type DELETE to confirm"
            className="h-9 rounded-md border border-input px-2.5 text-sm"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            autoFocus
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button variant="destructive" disabled={typed !== "DELETE" || busy} onClick={deleteAccount}>
              {busy ? "Deleting…" : "Delete account"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

type Webhook = { enabled: boolean; url: string | null; last_at: string | null; last_error: string | null };

function WebhookCard() {
  const [hook, setHook] = useState<Webhook | null>(null);
  const [url, setUrl] = useState("");
  const [secret, setSecret] = useState(""); // shown once, right after saving
  const [busy, setBusy] = useState(false);
  const [removing, setRemoving] = useState(false); // the confirm dialog

  function show(h: Webhook) {
    setHook(h);
    setUrl(h.url ?? "");
  }

  const load = async () => show(await getJSON<Webhook>("/account/webhook"));

  useEffect(() => {
    getJSON<Webhook>("/account/webhook").then(show, () => {}); // on error the card stays hidden
  }, []);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    try {
      await action();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  // also used with the saved address for "New secret"
  const save = (address: string) => run(async () => {
    const r = await sendJSON<{ url: string; secret: string }>("PUT", "/account/webhook", { url: address });
    setSecret(r.secret);
    await load();
    toast.success(address === hook?.url ? "New secret made. The old one no longer works." : "Webhook saved.");
  });

  const test = () => run(async () => {
    const r = await sendJSON<{ ok: boolean; status?: number; error?: string }>("POST", "/account/webhook/test");
    if (r.ok) toast.success(`Test sent. Your address answered ${r.status}.`);
    else toast.error(`Test failed: ${r.error}`);
  });

  const remove = () => run(async () => {
    setRemoving(false);
    await sendJSON("DELETE", "/account/webhook");
    setSecret("");
    await load();
    toast.success("Webhook removed.");
  });

  if (!hook?.enabled) return null; // not set up on this server

  return (
    <section className="mt-5 rounded-xl border bg-card px-5 py-4 shadow-xs">
      <h2 className="font-semibold">Webhook</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Send each document to your own address, like an n8n webhook. You get the data read from it, not the file.
        Saving an address makes a new secret.
      </p>
      <div className="mt-4 grid gap-1.5">
        <Label htmlFor="webhook-url">Address</Label>
        <div className="flex gap-2">
          <Input id="webhook-url" type="url" placeholder="https://" value={url} onChange={(e) => setUrl(e.target.value)} />
          <Button onClick={() => save(url)} disabled={busy || !url.trim() || url.trim() === hook.url}>Save</Button>
        </div>
      </div>
      {!hook.url && hook.last_error && <p className="mt-3 text-sm text-bad">{hook.last_error}</p>}

      {secret && (
        <div className="mt-4 rounded-lg border bg-muted/40 p-3 text-sm">
          <p className="font-medium">Your secret. Copy it now. It won&apos;t be shown again.</p>
          <div className="mt-2 flex gap-2">
            <code className="min-w-0 flex-1 truncate rounded bg-background px-2 py-1.5">{secret}</code>
            <Button variant="outline" size="sm" onClick={() => navigator.clipboard.writeText(secret).then(() => toast.success("Copied."), () => toast.error("Copy failed. Select the text instead."))}>
              Copy
            </Button>
          </div>
          <p className="mt-2 text-muted-foreground">
            Each request has an X-Signature header: sha256= and the HMAC-SHA256 of the body with this secret. Check it to know the
            request came from Crosscheck.
          </p>
        </div>
      )}

      {hook.url && (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <p className={`text-sm ${hook.last_error ? "text-bad" : "text-muted-foreground"}`}>
            {!hook.last_at
              ? "Nothing sent yet."
              : hook.last_error
                ? `Last send failed: ${hook.last_error}`
                : `Last sent ${new Date(hook.last_at).toLocaleString()}.`}
          </p>
          <div className="flex gap-2">
            <Button variant="outline" onClick={test} disabled={busy}>Send test</Button>
            <Button variant="outline" onClick={() => save(hook.url!)} disabled={busy}>New secret</Button>
            <Button variant="outline" onClick={() => setRemoving(true)} disabled={busy}>Remove</Button>
          </div>
        </div>
      )}

      <Dialog open={removing} onOpenChange={setRemoving}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remove your webhook?</DialogTitle>
            <DialogDescription>Documents stop going to this address. Events still waiting to be sent are dropped.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRemoving(false)}>Cancel</Button>
            <Button variant="destructive" onClick={remove} disabled={busy}>Remove</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
