import Link from "next/link";
import { cn } from "@/lib/utils";

export function Logo({ href = "/", className }: { href?: string; className?: string }) {
  return (
    <Link href={href} className={cn("display text-[19px] [font-stretch:140%] leading-none", className)}>
      Crosscheck
    </Link>
  );
}
