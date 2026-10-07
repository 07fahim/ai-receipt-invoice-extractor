"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { cn } from "@/lib/utils";

const REDUCE = "(prefers-reduced-motion: reduce)";
function onReduceChange(cb: () => void) {
  const m = matchMedia(REDUCE);
  m.addEventListener("change", cb);
  return () => m.removeEventListener("change", cb);
}

// Steps through a demo in a loop while it is on screen. With reduced motion it stays on `still`.
export function useSteps(durations: number[], still: number) {
  const ref = useRef<HTMLDivElement>(null);
  const [step, setStep] = useState(0);
  const [on, setOn] = useState(false);
  const reduced = useSyncExternalStore(onReduceChange, () => matchMedia(REDUCE).matches, () => false);
  useEffect(() => {
    if (reduced) return;
    const io = new IntersectionObserver(([e]) => setOn(e.isIntersecting), { threshold: 0.4 });
    io.observe(ref.current!);
    return () => io.disconnect();
  }, [reduced]);
  useEffect(() => {
    if (!on || reduced) return;
    const t = setTimeout(() => setStep((s) => (s + 1) % durations.length), durations[step]);
    return () => clearTimeout(t);
  }, [on, reduced, step, durations]);
  return { ref, step: reduced ? still : step, shown: on || reduced };
}

// The browser-window card the demos play in (same look as the old video frame).
export function DemoFrame({ frameRef, shown, label, className, children }: {
  frameRef: React.RefObject<HTMLDivElement | null>; shown: boolean; label: string; className?: string; children: React.ReactNode;
}) {
  return (
    <div ref={frameRef} data-shown={shown || undefined} role="img" aria-label={label}
      className={cn("rise overflow-hidden rounded-xl border bg-card shadow-[0_18px_40px_-18px_rgba(17,24,39,0.35)]", className)}>
      <div className="flex gap-1.5 border-b bg-background px-4 py-3" aria-hidden>
        <span className="size-2.5 rounded-full bg-border" />
        <span className="size-2.5 rounded-full bg-border" />
        <span className="size-2.5 rounded-full bg-border" />
      </div>
      <div aria-hidden className="@container relative aspect-[16/10] w-full overflow-hidden bg-background">{children}</div>
    </div>
  );
}

export function Cursor({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={cn("pointer-events-none absolute size-5 drop-shadow", className)}>
      <path d="M4 2.5v17.2l4.6-4.4 2.9 6.6 2.8-1.2-2.9-6.5h6.3z" className="fill-foreground stroke-card" strokeWidth="1.2" />
    </svg>
  );
}
