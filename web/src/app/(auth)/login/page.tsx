"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Suspense } from "react";
import { Button } from "@/components/ui/button";
import { Divider, Field, FormError, GoogleButton, LinkError, useAction } from "@/components/auth-form";
import { createClient } from "@/lib/supabase/client";

export default function LoginPage() {
  const router = useRouter();
  const { busy, error, run } = useAction();

  function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    run(async () => {
      const { error } = await createClient().auth.signInWithPassword({
        email: String(form.get("email")),
        password: String(form.get("password")),
      });
      if (error) throw error;
      router.replace("/app/upload");
      router.refresh();
    });
  }

  return (
    <div className="grid gap-5">
      <div>
        <h1 className="text-xl font-semibold">Log in</h1>
        <p className="mt-1 text-sm text-muted-foreground">Welcome back.</p>
      </div>
      <Suspense>
        <LinkError />
      </Suspense>
      <GoogleButton />
      <Divider />
      <form onSubmit={submit} className="grid gap-4">
        <Field id="email" label="Email" type="email" autoComplete="email" />
        <Field id="password" label="Password" type="password" autoComplete="current-password" />
        <FormError message={error} />
        <Button type="submit" className="h-10" disabled={busy}>
          {busy ? "Logging in…" : "Log in"}
        </Button>
      </form>
      <div className="flex justify-between text-sm">
        <Link href="/forgot-password" className="text-primary hover:underline">Forgot password?</Link>
        <Link href="/signup" className="text-primary hover:underline">Create an account</Link>
      </div>
    </div>
  );
}
