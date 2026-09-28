import Link from "next/link";

export function Logo({ href = "/" }: { href?: string }) {
  return (
    <Link href={href} className="flex items-center gap-2 text-[17px] font-bold">
      <span className="size-5.5 rounded-[6px] bg-primary" aria-hidden />
      Crosscheck
    </Link>
  );
}
