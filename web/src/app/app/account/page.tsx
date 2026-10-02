"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { sendJSON } from "@/lib/api";
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
