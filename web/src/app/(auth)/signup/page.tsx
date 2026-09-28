"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Divider, Field, FormError, GoogleButton, useAction } from "@/components/auth-form";
import { createClient } from "@/lib/supabase/client";

export default function SignupPage() {
  const router = useRouter();
  const { busy, error, run } = useAction();
  const [email, setEmail] = useState<string | null>(null); // set once the code has been sent
  const [resent, setResent] = useState(false);

  function signUp(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const address = String(form.get("email"));
    run(async () => {
      const { error } = await createClient().auth.signUp({
        email: address,
        password: String(form.get("password")),
        // the email has a 6-digit code (custom template) or a link (Supabase's default); the link signs in here
        options: { emailRedirectTo: `${location.origin}/auth/callback` },
      });
      if (error) throw error;
      setEmail(address);
    });
  }

  function verify(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const code = String(new FormData(e.currentTarget).get("code")).trim();
    run(async () => {
      const { error } = await createClient().auth.verifyOtp({ email: email!, token: code, type: "signup" });
      if (error) throw error;
      router.replace("/app/upload");
      router.refresh();
    });
  }

  if (email) {
    return (
      <div className="grid gap-5">
        <div>
          <h1 className="text-xl font-semibold">Check your email</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            We sent an email to <span className="font-medium text-foreground">{email}</span>. Enter the 6-digit code from it, or
            click the link in it.
          </p>
        </div>
        <form onSubmit={verify} className="grid gap-4">
          <Field id="code" label="Code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} autoFocus />
          <FormError message={error} />
          <Button type="submit" className="h-10" disabled={busy}>
            {busy ? "Checking…" : "Confirm email"}
          </Button>
        </form>
        <p className="text-sm text-muted-foreground">
          {resent ? "A new code is on its way." : "No email? Check spam, or "}
          {!resent && (
            <button
              type="button"
              className="text-primary hover:underline"
              onClick={() =>
                run(async () => {
                  const { error } = await createClient().auth.resend({ type: "signup", email });
                  if (error) throw error;
                  setResent(true);
                })
              }
            >
              send a new code
            </button>
          )}
        </p>
      </div>
    );
  }

  return (
    <div className="grid gap-5">
      <div>
        <h1 className="text-xl font-semibold">Create your account</h1>
        <p className="mt-1 text-sm text-muted-foreground">Start turning receipts into clean data.</p>
      </div>
      <GoogleButton />
      <Divider />
      <form onSubmit={signUp} className="grid gap-4">
        <Field id="email" label="Email" type="email" autoComplete="email" />
        <Field id="password" label="Password" type="password" autoComplete="new-password" minLength={8} />
        <p className="-mt-2 text-xs text-muted-foreground">At least 8 characters.</p>
        <FormError message={error} />
        <Button type="submit" className="h-10" disabled={busy}>
          {busy ? "Creating account…" : "Create account"}
        </Button>
      </form>
      <p className="text-sm text-muted-foreground">
        Already have an account? <Link href="/login" className="text-primary hover:underline">Log in</Link>
      </p>
    </div>
  );
}
