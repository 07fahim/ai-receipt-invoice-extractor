import { NextResponse, type NextRequest } from "next/server";
import { createClient } from "@/lib/supabase/server";

// Google sign-in and emailed links (password reset) return here with a one-time code, exchanged for a session cookie.
// next: where to go afterwards; only a path on this site, so the link can't send anyone elsewhere.
export async function GET(request: NextRequest) {
  const { searchParams, origin } = request.nextUrl;
  const code = searchParams.get("code");
  const next = searchParams.get("next") ?? "";
  const target = next.startsWith("/") && !next.startsWith("//") ? next : "/app/upload";
  if (code) {
    const supabase = await createClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) return NextResponse.redirect(`${origin}${target}`);
  }
  return NextResponse.redirect(`${origin}/login?error=link`);
}
