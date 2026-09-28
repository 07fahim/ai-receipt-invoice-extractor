"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { BarChart3, ClipboardCheck, FileText, LogOut, Upload } from "lucide-react";
import { Logo } from "@/components/logo";
import { getJSON } from "@/lib/api";
import { createClient } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/app/upload", label: "Upload", icon: Upload },
  { href: "/app/review", label: "Review", icon: ClipboardCheck },
  { href: "/app/documents", label: "Documents", icon: FileText },
  { href: "/app/dashboard", label: "Dashboard", icon: BarChart3 },
];

export function AppNav({ email }: { email: string }) {
  const path = usePathname();
  const router = useRouter();
  const [waiting, setWaiting] = useState(0);

  useEffect(() => {
    getJSON<{ by_status: Record<string, number> }>("/stats")
      .then((s) => setWaiting(s.by_status.needs_review ?? 0))
      .catch(() => {}); // the count is a hint; pages show their own errors
  }, [path]);

  async function signOut() {
    await createClient().auth.signOut();
    router.replace("/");
    router.refresh();
  }

  return (
    <nav
      aria-label="Main"
      className="fixed inset-x-0 bottom-0 z-20 flex justify-around border-t bg-card px-1 py-1.5 md:sticky md:top-0 md:h-screen md:flex-col md:justify-start md:gap-0.5 md:border-t-0 md:border-r md:px-3 md:py-5"
    >
      <div className="hidden px-2.5 pb-5 md:block">
        <Logo href="/app/upload" />
      </div>
      {LINKS.map(({ href, label, icon: Icon }) => {
        const active = path.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "relative flex flex-col items-center gap-0.5 rounded-lg px-3 py-1.5 text-[11px] font-medium text-foreground/75 transition-colors hover:bg-secondary md:flex-row md:gap-2.5 md:px-2.5 md:py-2 md:text-[15px]",
              active && "text-primary md:bg-accent",
            )}
          >
            <Icon className={cn("size-[18px] shrink-0", active ? "text-primary" : "text-muted-foreground")} aria-hidden />
            {label}
            {href === "/app/review" && waiting > 0 && (
              <span
                aria-label={`${waiting} waiting`}
                className="absolute top-0 right-2 rounded-full bg-warn-soft px-1.5 text-[10px] leading-4 text-warn md:static md:ml-auto md:px-2 md:text-xs md:leading-5"
              >
                {waiting}
              </span>
            )}
          </Link>
        );
      })}
      <div className="mt-auto hidden items-center gap-2.5 border-t px-2.5 pt-3 md:flex">
        <span className="grid size-8 shrink-0 place-items-center rounded-full bg-accent text-[13px] font-semibold text-primary" aria-hidden>
          {email.slice(0, 1).toUpperCase()}
        </span>
        <span className="min-w-0 flex-1 truncate text-[13px]" title={email}>{email}</span>
        <button onClick={signOut} className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary" aria-label="Log out" title="Log out">
          <LogOut className="size-4" />
        </button>
      </div>
    </nav>
  );
}
