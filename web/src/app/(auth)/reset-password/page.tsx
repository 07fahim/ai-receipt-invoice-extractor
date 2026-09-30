"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Field, FormError, useAction } from "@/components/auth-form";
import { createClient } from "@/lib/supabase/client";

// Reached from the reset email's link: /auth/callback has already signed the user in.
export default function ResetPasswordPage() {
  const router = useRouter();
  const { busy, error, run } = useAction();

  function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const password = String(new FormData(e.currentTarget).get("password"));
    run(async () => {
      const { error } = await createClient().auth.updateUser({ password });
      if (error) throw new Error(error.message.includes("session") ? "This reset link has expired. Please request a new one." : error.message);
      router.replace("/app/upload");
      router.refresh();
    });
  }

  return (
    <div className="grid gap-5">
      <div>
        <h1 className="text-xl font-semibold">Set a new password</h1>
        <p className="mt-1 text-sm text-muted-foreground">At least 8 characters.</p>
      </div>
      <form onSubmit={submit} className="grid gap-4">
        <Field id="password" label="New password" type="password" autoComplete="new-password" minLength={8} autoFocus />
        <FormError message={error} />
        <Button type="submit" className="h-10" disabled={busy}>
          {busy ? "Saving…" : "Save new password"}
        </Button>
      </form>
      <Link href="/forgot-password" className="text-sm text-primary hover:underline">Request a new link</Link>
    </div>
  );
}
