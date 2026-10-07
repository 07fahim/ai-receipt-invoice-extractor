"use client";

import { cn } from "@/lib/utils";
import { Cursor, DemoFrame, useSteps } from "@/components/demo-frame";

type Scene = {
  shop: string; lines: [string, string, string][]; subtotal: string; bad: number; fixed: string;
  checks: string[]; fix: string;
};

const SCENES: Scene[] = [
  {
    shop: "MAPLE STREET MARKET", subtotal: "32.65", bad: 3, fixed: "4.47",
    lines: [["ORGANIC BANANAS", "2.31 lb @ 0.79", "1.82"], ["GREEK YOGURT 32OZ", "", "5.49"], ["EGGS LARGE 12CT", "", "3.89"],
      ["AVOCADO HASS", "3 @ 1.49", "4.97"], ["SOURDOUGH LOAF", "", "4.99"], ["COFFEE BEANS 12OZ", "", "11.99"]],
    checks: ["Line items add up to 33.15. The subtotal is 32.65.", "3 x 1.49 = 4.47. The line says 4.97."],
    fix: "Did you mean 4.47 instead of 4.97? Then every sum adds up.",
  },
  {
    shop: "মা-বাবার ফল ভান্ডার", subtotal: "1,230", bad: 2, fixed: "240",
    lines: [["আম (হিমসাগর)", "2 x 140", "280"], ["কলা (সাগর)", "1 x 60", "60"], ["কমলা (মালটা)", "2 x 120", "280"],
      ["আপেল (রেডেল গালা)", "1 x 200", "200"], ["আঙ্গুর (কালো)", "1 x 220", "220"], ["পেঁপে (পাকা)", "1 x 80", "80"], ["ড্রাগন ফল", "1 x 150", "150"]],
    checks: ["Line items add up to 1,270. The subtotal is 1,230.", "2 x 120 = 240. The line says 280."],
    fix: "Did you mean 240 instead of 280? Then every sum adds up.",
  },
];
// per scene: reading, flagged, fix shown, cursor to Apply, click, all pass
const PHASES = [900, 1800, 1700, 900, 450, 2400];
const DURATIONS = SCENES.flatMap(() => PHASES);

// the review page's check names for the two checks that fail here
const LABELS = ["Line items match subtotal", "Quantity × price = amount"];

export function DemoFix({ className }: { className?: string }) {
  const { ref, step, shown } = useSteps(DURATIONS, 2); // reduced motion: the flag with its fix
  const s = SCENES[Math.floor(step / PHASES.length)];
  const p = step % PHASES.length;
  const flagged = p >= 1 && p <= 4;
  const passed = p === 5;
  return (
    <DemoFrame frameRef={ref} shown={shown} className={className}
      label="Demo: a receipt line that does not add up is flagged, the suggested fix is applied and every check passes. Shown on a US grocery receipt and a handwritten Bangla memo.">
      <div className="absolute inset-0 grid grid-cols-[40%_1fr] @md:grid-cols-[46%_1fr] @xl:grid-cols-[50%_1fr] text-[9px] leading-snug @md:text-[11px] @xl:text-[13.5px]">
        <div className="border-r bg-card @md:bg-background @md:p-4 @xl:p-5">
          <div className="relative overflow-hidden bg-card px-3 py-3 font-mono leading-[1.8] tracking-tight @md:rounded-lg @md:border @md:px-4 @md:shadow-xs @xl:py-4 @xl:text-[0.9em]">
            <div className={cn("absolute inset-x-0 top-0 h-1/4 bg-gradient-to-b from-transparent to-primary/15",
              p === 0 && shown ? "translate-y-[400%] opacity-100 transition-transform duration-[900ms] ease-linear" : "-translate-y-full opacity-0")} />
            <p className="mb-2 text-center font-semibold text-balance">{s.shop}</p>
            {s.lines.map(([name, qty, amount], n) => (
              <div key={s.shop + n} className={cn("-mx-1 flex gap-1.5 rounded px-1 transition-colors duration-500",
                n === s.bad && flagged && "bg-warn-soft text-warn", n === s.bad && passed && "bg-ok-soft text-ok")}>
                <span className="min-w-0 truncate">{name}</span>
                {/* on small screens only the flagged line keeps its quantity */}
                {qty && <span className={cn("shrink-0 opacity-70", n !== s.bad && "hidden @md:inline")}>{qty}</span>}
                <span key={n === s.bad && p >= 4 ? "new" : "old"}
                  className={cn("ml-auto shrink-0 pl-1 tabular-nums", n === s.bad && p >= 4 && "animate-in fade-in slide-in-from-top-2 duration-300")}>
                  {n === s.bad && p >= 4 ? s.fixed : amount}
                </span>
              </div>
            ))}
            <div className="mt-1.5 flex justify-between border-t pt-1.5 font-semibold"><span>SUBTOTAL</span><span className="tabular-nums">{s.subtotal}</span></div>
          </div>
        </div>
        <div className="flex flex-col bg-background p-2.5 font-sans @md:p-4 @xl:p-5">
          <div className="rounded-lg border bg-card p-2.5 shadow-xs @md:p-3.5">
            <div className="flex items-center justify-between gap-2 font-semibold">
              Checks
              <span className={cn("rounded-full px-2 py-0.5 font-medium transition-colors duration-500",
                p === 0 ? "bg-secondary text-muted-foreground" : passed ? "bg-ok-soft text-ok" : "bg-warn-soft text-warn")}>
                {p === 0 ? "Reading..." : passed ? "All checks pass" : `${s.checks.length} to fix`}
              </span>
            </div>
            <div className={cn("grid transition-all duration-500", p >= 2 && p <= 4 ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0")}>
              <div className="overflow-hidden">
                <div className="mt-2 rounded-md border border-primary/30 bg-primary/5 p-2 @md:p-2.5">
                  <p className="hidden font-medium @md:block">Suggested fix</p>
                  <p className="text-muted-foreground">{s.fix}</p>
                  <span className="relative mt-1.5 inline-block">
                    <span className={cn("inline-block rounded-md bg-primary px-2.5 py-0.5 font-medium text-primary-foreground transition-transform duration-150 @md:py-1",
                      p === 4 && "scale-90")}>Apply</span>
                    <Cursor className={cn("top-2.5 left-6 transition-all duration-700 ease-out @md:top-3 @md:left-8",
                      p === 3 || p === 4 ? "translate-x-0 translate-y-0 opacity-100" : "translate-x-16 translate-y-8 opacity-0")} />
                  </span>
                </div>
              </div>
            </div>
            <ul className="mt-1.5 divide-y">
              {s.checks.map((c, n) => (
                <li key={c} className={cn("flex gap-1.5 py-1.5 transition-colors duration-500", p === 0 && "text-muted-foreground",
                  flagged && "font-medium text-warn")}>
                  <span className={cn("w-3 shrink-0 text-center", !flagged && p > 0 && "text-ok")}>{p === 0 ? "·" : flagged ? "!" : "✓"}</span>
                  <span>
                    <span className={cn(flagged && "hidden @md:inline")}>{LABELS[n]}</span>
                    <span className={cn("grid transition-all duration-500", flagged ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0")}>
                      <span className="overflow-hidden font-normal">{c}</span>
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </DemoFrame>
  );
}
