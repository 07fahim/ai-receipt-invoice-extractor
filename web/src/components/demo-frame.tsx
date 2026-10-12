"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Pause, Play } from "lucide-react";
import { cn } from "@/lib/utils";

const REDUCE = "(prefers-reduced-motion: reduce)";
function onReduceChange(cb: () => void) {
  const m = matchMedia(REDUCE);
  m.addEventListener("change", cb);
  return () => m.removeEventListener("change", cb);
}

// Steps through a demo in a loop while it is on screen, until paused. With reduced motion it stays on `still`.
export function useSteps(durations: number[], still: number) {
  const ref = useRef<HTMLDivElement>(null);
  const [step, setStep] = useState(0);
  const [on, setOn] = useState(false);
  const [seen, setSeen] = useState(false); // the card fades in once and stays; `on` only runs the timer
  const [paused, setPaused] = useState(false);
  const reduced = useSyncExternalStore(onReduceChange, () => matchMedia(REDUCE).matches, () => false);
  useEffect(() => {
    if (reduced) return;
    const io = new IntersectionObserver(([e]) => {
      setOn(e.isIntersecting);
      if (e.isIntersecting) setSeen(true);
    }, { threshold: 0.4 });
    io.observe(ref.current!);
    return () => io.disconnect();
  }, [reduced]);
  useEffect(() => {
    if (!on || reduced || paused) return;
    const t = setTimeout(() => setStep((s) => (s + 1) % durations.length), durations[step]);
    return () => clearTimeout(t);
  }, [on, reduced, paused, step, durations]);
  const pause = reduced ? undefined : { paused, toggle: () => setPaused((p) => !p) };
  return { ref, step: reduced ? still : step, shown: seen || reduced, pause };
}

// The browser-window card the demos play in (same look as the old video frame).
export function DemoFrame({ frameRef, shown, label, pause, className, children }: {
  frameRef: React.RefObject<HTMLDivElement | null>; shown: boolean; label: string;
  pause?: { paused: boolean; toggle: () => void }; className?: string; children: React.ReactNode;
}) {
  return (
    <div ref={frameRef} data-shown={shown || undefined}
      className={cn("rise overflow-hidden rounded-xl border bg-card shadow-[0_18px_40px_-18px_rgba(17,24,39,0.35)]", className)}>
      <div className="flex h-10 items-center gap-1.5 border-b bg-background px-4">
        <span className="size-2.5 rounded-full bg-border" aria-hidden />
        <span className="size-2.5 rounded-full bg-border" aria-hidden />
        <span className="size-2.5 rounded-full bg-border" aria-hidden />
        {pause && (
          <button type="button" onClick={pause.toggle} aria-label={pause.paused ? "Play the demo" : "Pause the demo"}
            className="-mr-2 ml-auto grid size-8 place-items-center rounded-md text-muted-foreground hover:bg-secondary hover:text-foreground">
            {pause.paused ? <Play className="size-3.5" /> : <Pause className="size-3.5" />}
          </button>
        )}
      </div>
      <div role="img" aria-label={label} className="@container relative aspect-[16/10] w-full overflow-hidden bg-background">
        <div aria-hidden className="contents">{children}</div>
      </div>
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
