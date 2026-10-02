import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

const AUTH_PAGES = ["/login", "/signup", "/forgot-password"];

// Refreshes the Supabase session on every page request and keeps signed-out visitors out of /app.
// The API checks the token itself on every call; this is only the page-level redirect.
export async function proxy(request: NextRequest) {
  let response = NextResponse.next({ request });
  // Not set up yet (no web/.env.local): public pages still work; /app needs the settings.
  if (!process.env.NEXT_PUBLIC_SUPABASE_URL || !process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY) {
    if (request.nextUrl.pathname.startsWith("/app")) {
      return new NextResponse("Sign-in is not set up: add web/.env.local (see web/.env.example).", { status: 503 });
    }
    return response;
  }
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet, headers) {
          cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
          response = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) => response.cookies.set(name, value, options));
          Object.entries(headers).forEach(([k, v]) => response.headers.set(k, v)); // no caching of signed-in pages
        },
      },
    },
  );
  // Nothing may run between creating the client and getClaims(), or sessions get lost.
  const { data } = await supabase.auth.getClaims();
  const signedIn = !!data?.claims;
  const path = request.nextUrl.pathname;

  const redirect = (to: string) => {
    const url = request.nextUrl.clone();
    url.pathname = to;
    url.search = "";
    const r = NextResponse.redirect(url);
    response.cookies.getAll().forEach((c) => r.cookies.set(c)); // keep refreshed session cookies
    return r;
  };
  if (!signedIn && path.startsWith("/app")) return redirect("/login");
  if (signedIn && AUTH_PAGES.includes(path)) return redirect("/app/upload");
  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)"],
};
