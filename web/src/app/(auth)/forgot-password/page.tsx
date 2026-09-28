"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Field, FormError, useAction } from "@/components/auth-form";
import { createClient } from "@/lib/supabase/client";

export default function ForgotPasswordPage() {
  const router = useRouter();
  const { busy, error, run } = useAction();
  const [email, setEmail] = useState<string | null>(null); // set once the code has been sent

  function sendCode(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const address = String(new FormData(e.currentTarget).get("email"));
    run(async () => {
      const { error } = await createClient().auth.resetPasswordForEmail(address);
      if (error) throw error;
      setEmail(address);
    });
  }

  function reset(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    run(async () => {
      const supabase = createClient();
      const { error } = await supabase.auth.verifyOtp({ email: email!, token: String(form.get("code")).trim(), type: "recovery" });
      if (error) throw error;
      const { error: updateError } = await supabase.auth.updateUser({ password: String(form.get("password")) });
      if (updateError) throw updateError;
      router.replace("/app/upload");
      router.refresh();
    });
  }

  return (
    <div className="grid gap-5">
      <div>
        <h1 className="text-xl font-semibold">Reset your password</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {email ? (
            <>Enter the 6-digit code we sent to <span className="font-medium text-foreground">{email}</span> and a new password.</>
          ) : (
            "We'll email you a 6-digit code."
          )}
        </p>
      </div>
      {email ? (
        <form onSubmit={reset} className="grid gap-4">
          <Field id="code" label="Code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} autoFocus />
          <Field id="password" label="New password" type="password" autoComplete="new-password" minLength={8} />
          <FormError message={error} />
          <Button type="submit" className="h-10" disabled={busy}>
            {busy ? "Saving…" : "Save new password"}
          </Button>
        </form>
      ) : (
        <form onSubmit={sendCode} className="grid gap-4">
          <Field id="email" label="Email" type="email" autoComplete="email" />
          <FormError message={error} />
          <Button type="submit" className="h-10" disabled={busy}>
            {busy ? "Sending…" : "Send code"}
          </Button>
        </form>
      )}
      <Link href="/login" className="text-sm text-primary hover:underline">Back to log in</Link>
    </div>
  );
}
