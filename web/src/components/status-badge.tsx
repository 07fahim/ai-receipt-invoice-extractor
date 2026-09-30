import type { Status } from "@/lib/api";
import { cn } from "@/lib/utils";

const STYLES: Record<Status, [string, string]> = {
  processing: ["Processing", "bg-accent text-primary"],
  passed: ["Passed", "bg-ok-soft text-ok"],
  needs_review: ["Needs review", "bg-warn-soft text-warn"],
  failed: ["Failed", "bg-bad-soft text-bad"],
  reviewed: ["Reviewed", "bg-secondary text-foreground/75"],
};

// Status is always text plus colour, never colour alone.
export function StatusBadge({ status, className }: { status: Status; className?: string }) {
  const [label, style] = STYLES[status];
  return (
    <span className={cn("inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-medium", style, className)}>
      <span className="size-1.5 rounded-full bg-current" aria-hidden />
      {label}
    </span>
  );
}
