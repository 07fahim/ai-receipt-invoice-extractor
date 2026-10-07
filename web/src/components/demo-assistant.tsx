"use client";

import { useEffect, useState } from "react";
import { Check, MessageSquareText, SendHorizontal } from "lucide-react";
import { cn } from "@/lib/utils";
import { DemoFrame, useSteps } from "@/components/demo-frame";

type Chat = { doc: [string, string][]; flagged: number; shop: string; date?: string; question: string; chip: string; answer: string[] };

// answers recorded from the live assistant (doc #97 on 2026-10-08, doc #74 earlier)
const CHATS: Chat[] = [
  {
    shop: "HARBOR FRESH MARKET", date: "Date: 10/03/2026", flagged: 5, question: "Why is this flagged?", chip: "Read document #97",
    answer: ["Document #97 is flagged for the following reasons:",
      "Is 10/03/2026 day first or month first? Readings: 3 Oct 2026 (month first), 10 Mar 2026 (day first).",
      "In the AI's reading: Line items add up to 26.85. The subtotal is 29.85."],
    doc: [["CHICKEN BREAST", "11.73"], ["WHOLE MILK 1 GAL", "4.29"], ["EGGS LARGE 12CT", "3.89"], ["BANANAS", "1.45"],
      ["SOURDOUGH BREAD", "5.49"], ["SUBTOTAL", "29.85"]],
  },
  {
    shop: "মা-বাবার ফল ভান্ডার", flagged: 2, question: "এই রসিদে সমস্যা কী?", chip: "Read document #74",
    answer: ["নথি #74-এ এই সমস্যাগুলো রয়েছে:",
      "লাইনের পরিমাণ এবং একক মূল্যের গুণফল ঠিক নেই। এআই-এর পাঠ অনুযায়ী: ২ x ১২০ = ২৪০.০০ বিডিটি। কিন্তু লাইনটিতে বলা হয়েছে ২৮০.০০ বিডিটি।",
      "দয়া করে ছবিটির সাথে এই লাইনগুলো মিলিয়ে দেখুন।"],
    doc: [["আম (হিমসাগর)", "280"], ["কলা (সাগর)", "60"], ["কমলা (মালটা)", "280"], ["আপেল (রেডেল গালা)", "200"],
      ["আঙ্গুর (কালো)", "220"], ["পেঁপে (পাকা)", "80"], ["ড্রাগন ফল", "150"]],
  },
];
// per scene: page, panel slides in, question typed, thinking, answer
const PHASES = [900, 700, 1400, 1100, 4800];
const DURATIONS = CHATS.flatMap(() => PHASES);

function Avatar({ className }: { className?: string }) {
  return (
    <span className={cn("grid size-[1.9em] flex-none place-items-center rounded-md bg-primary text-primary-foreground", className)}>
      <MessageSquareText className="size-[1.1em]" />
    </span>
  );
}

export function DemoAssistant({ className }: { className?: string }) {
  const { ref, step, shown } = useSteps(DURATIONS, 4); // reduced motion: question and answer
  const c = CHATS[Math.floor(step / PHASES.length)];
  const p = step % PHASES.length;
  const [typed, setTyped] = useState(0);
  useEffect(() => {
    if (p !== 2) return;
    const t = setInterval(() => setTyped((k) => Math.min(k + 1, c.question.length)), 45);
    return () => { clearInterval(t); setTyped(0); };
  }, [p, c]);
  const question = c.question.slice(0, typed);
  return (
    <DemoFrame frameRef={ref} shown={shown} className={className}
      label="Demo: the assistant is asked why a receipt is flagged, in English on a US receipt and in Bangla on a handwritten memo, and answers with the numbers the checks found.">
      <div className="absolute inset-0 text-[9px] leading-snug @md:text-[11px] @xl:text-[13.5px]">
        <div className={cn("h-full w-[40%] border-r bg-card transition-opacity duration-700 @md:w-[50%] @md:bg-background @md:p-4 @xl:w-[58%] @xl:p-5",
          p > 0 && "opacity-60")}>
          <div className="bg-card px-3 py-3 font-mono leading-[1.8] tracking-tight @md:rounded-lg @md:border @md:px-4 @md:shadow-xs @xl:py-4 @xl:text-[0.9em]">
            <p className="mb-2 text-center font-semibold text-balance">{c.shop}</p>
            {/* the date can be read two ways: a real flag on that receipt too */}
            {c.date && <p className="-mx-1 mb-1.5 rounded bg-warn-soft px-1 text-warn">{c.date}</p>}
            {c.doc.map(([name, amount], n) => (
              <div key={c.shop + n} className={cn("-mx-1 flex gap-1.5 rounded px-1",
                n === c.flagged && "bg-warn-soft text-warn", name === "SUBTOTAL" && "mt-1.5 font-semibold")}>
                <span className="min-w-0 truncate">{name}</span>
                <span className="ml-auto shrink-0 pl-1 tabular-nums">{amount}</span>
              </div>
            ))}
          </div>
        </div>
        <div className={cn("absolute inset-y-0 right-0 flex w-[60%] flex-col border-l bg-card transition-transform duration-700 ease-out @md:w-[50%] @xl:w-[42%]",
          p >= 1 ? "translate-x-0 shadow-[-12px_0_30px_-20px_rgba(17,24,39,0.35)]" : "translate-x-full")}>
          <div className="flex items-center gap-1.5 border-b px-2.5 py-1.5 font-semibold @md:px-3 @md:py-2"><Avatar />Assistant</div>
          <div className="flex min-h-0 flex-1 flex-col justify-end gap-1.5 overflow-hidden p-2 @md:gap-3 @md:p-3">
            {/* small frames have no input box: the question types straight into its bubble */}
            {p >= 2 && (
              <p className={cn("ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-2.5 py-1 text-primary-foreground @md:px-3 @md:py-1.5",
                p === 2 && "@md:hidden")}>{p === 2 ? question : c.question}</p>
            )}
            {p === 3 && (
              <div className="flex gap-1.5">
                <Avatar className="@max-md:hidden" />
                <div className="flex items-center gap-1 rounded-2xl rounded-tl-sm bg-muted/60 px-2.5 py-2">
                  {["", "[animation-delay:150ms]", "[animation-delay:300ms]"].map((d) => (
                    <span key={d} className={cn("size-1.5 animate-bounce rounded-full bg-muted-foreground", d)} />
                  ))}
                </div>
              </div>
            )}
            {p === 4 && (
              <div key={c.chip} className="flex gap-1.5 animate-in fade-in slide-in-from-bottom-1 duration-500">
                <Avatar className="@max-md:hidden" />
                <div className="min-w-0 flex-1">
                  <span className="mb-1 inline-flex items-center gap-1 rounded-full bg-muted px-1.5 py-0.5 text-muted-foreground @md:px-2">
                    <Check className="size-[1em] text-ok" />{c.chip}
                  </span>
                  <div className="space-y-1 rounded-2xl rounded-tl-sm border bg-muted/40 px-2.5 py-1.5 @md:space-y-1.5 @md:px-3 @md:py-2">
                    {c.answer.map((a) => <p key={a}>{a}</p>)}
                  </div>
                </div>
              </div>
            )}
          </div>
          <div className="hidden border-t p-2.5 @md:block">
            <div className="flex items-center gap-1.5 rounded-lg border bg-background py-1 pr-1 pl-2">
              <span className="min-h-[1.4em] min-w-0 flex-1 truncate">
                {p === 2 && question}
                {p === 2 && <span className="ml-px inline-block h-[1.1em] w-px translate-y-[0.15em] animate-pulse bg-foreground" />}
              </span>
              <span className="grid size-[1.9em] flex-none place-items-center rounded-md bg-primary text-primary-foreground">
                <SendHorizontal className="size-[1em]" />
              </span>
            </div>
          </div>
        </div>
      </div>
    </DemoFrame>
  );
}
