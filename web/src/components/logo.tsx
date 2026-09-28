import Image from "next/image";
import Link from "next/link";
import { cn } from "@/lib/utils";

// The Crosscheck logo (icon + wordmark), trimmed from assests/logo.png.
export function Logo({ href = "/", className }: { href?: string; className?: string }) {
  return (
    <Link href={href} className={cn("inline-flex shrink-0", className)}>
      <Image src="/logo.png" alt="Crosscheck" width={1758} height={396} priority className="h-[34px] w-auto" />
    </Link>
  );
}
