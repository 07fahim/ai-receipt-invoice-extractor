import { type EmailOtpType } from "@supabase/supabase-js";
import { NextResponse, type NextRequest } from "next/server";
import { createClient } from "@/lib/supabase/server";

// Links in our emails (sign-up confirmation, password reset) come here with a one-time token hash, checked on the
// server. Unlike /auth/callback it needs nothing stored in the browser, so the link works in any browser or phone.
// next: where to go afterwards; only a path on this site.
export async function GET(request: NextRequest) {
  const { searchParams, origin } = request.nextUrl;
  const tokenHash = searchParams.get("token_hash");
  const type = searchParams.get("type") as EmailOtpType | null;
  const next = searchParams.get("next") ?? "";
  const target = next.startsWith("/") && !next.startsWith("//") ? next : "/app/upload";
  if (tokenHash && type) {
    const supabase = await createClient();
    const { error } = await supabase.auth.verifyOtp({ type, token_hash: tokenHash });
    if (!error) return NextResponse.redirect(`${origin}${target}`);
  }
  return NextResponse.redirect(`${origin}/login?error=link`);
}
