import Image from "next/image";
import Link from "next/link";
import { Archive, Calculator, ClipboardCheck, Download, Lock, MessageCircle, ScanText, Store, Trash2, Upload, Wallet } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DemoVideo } from "@/components/demo-video";
import { Logo } from "@/components/logo";
import { ThemeToggle } from "@/components/theme-toggle";
import { cn } from "@/lib/utils";

const features = [
  { icon: Upload, title: "Upload in batches", text: "Drop up to 20 photos or PDFs at once. Most are read in about five seconds." },
  { icon: ClipboardCheck, title: "Review only what needs it", text: "Each flagged field sits next to the original. The reason is shown too." },
  { icon: Download, title: "Export anywhere", text: "Download CSV, Excel or a QuickBooks bill import." },
];

// Who it is for: the paper that comes in from outside, which a POS or accounting system does not capture.
const useCases = [
  { icon: Calculator, title: "Bookkeepers", docs: "Receipts · invoices",
    text: "Upload a client's month of paperwork at once. You only check the ones that don't add up." },
  { icon: Store, title: "Restaurants and shops", docs: "Produce · meat · repairs",
    text: "Every supplier bill looks different. They all end up in one spreadsheet." },
  { icon: Wallet, title: "Expense claims", docs: "Fuel · taxi · supplies",
    text: "Staff photograph their receipts. You check the flagged ones and export the rest." },
  { icon: Archive, title: "Year-end and audits", docs: "Last year's receipts",
    text: "Clear a backlog 20 at a time. Duplicates are caught before they count twice." },
];

const questions = ["How much did I spend last month?", "Which bills are due this week?", "Why is this receipt flagged?"];

const checks = [
  ["Line items match the subtotal", "After any line discounts"],
  ["Totals add up", "Subtotal + tax + service − discount"],
  ["Each line adds up", "Quantity × unit price"],
  ["Dates are valid", "Unclear dates like 05/11 go to review"],
  ["Nothing is missing", "Total, line items and a valid currency"],
  ["No duplicates", "The same invoice uploaded twice is flagged"],
];

// The sample receipt's lines and checks, as the app would show them.
const TAPE: [string, string, "ok" | "flag" | ""][] = [
  ["Power Veg Bowl", "4.99", ""],
  ["No Sour Cream", "0.00", ""],
  ["No Cheese", "0.00", ""],
  ["Rg Orange Crsh", "1.99", ""],
  ["= Subtotal", "6.98", "ok"],
  ["+ Tax", "0.63", ""],
  ["= Total", "7.61", "ok"],
  ["Currency", "USD", "ok"],
  ["Date 9/1/2016", "?", "flag"],
];

const privacy = [
  { icon: Lock, title: "Only you see your files", text: "Other users can't see your documents." },
  { icon: Trash2, title: "Delete anytime", text: "Remove one document or your whole account." },
  { icon: ScanText, title: "Read by Google Gemini", text: "This demo uses Gemini's free plan. Google may use files to improve its AI. Please upload samples." },
];

export default function Home() {
  return (
    <div className="bg-card">
      <header className="sticky top-0 z-10 border-b bg-card/85 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
          <Logo />
          <nav className="flex items-center gap-7 text-sm font-medium text-foreground/80">
            <a href="#who" className="hidden whitespace-nowrap hover:text-foreground lg:block">Who it&apos;s for</a>
            <a href="#assistant" className="hidden whitespace-nowrap hover:text-foreground lg:block">Assistant</a>
            <a href="#features" className="hidden whitespace-nowrap hover:text-foreground lg:block">Features</a>
            <a href="#checks" className="hidden whitespace-nowrap hover:text-foreground lg:block">Checks</a>
            <a href="#privacy" className="hidden whitespace-nowrap hover:text-foreground lg:block">Privacy</a>
            <ThemeToggle />
            <Link href="/login" className="whitespace-nowrap hover:text-foreground">Log in</Link>
            <Button asChild><Link href="/signup">Get started</Link></Button>
          </nav>
        </div>
      </header>

      <main>
        <section className="px-6">
          <div className="mx-auto grid max-w-6xl items-center gap-14 pt-14 pb-20 lg:grid-cols-[1fr_1.1fr] lg:pt-20">
          <div>
            <p className="text-xs font-medium tracking-[0.12em] text-muted-foreground uppercase">Receipts and invoices to spreadsheet rows</p>
            <h1 className="display mt-4 text-[clamp(40px,4.6vw,64px)]">
              Every receipt read <span className="text-primary">and checked</span>
            </h1>
            <p className="mt-6 max-w-xl text-lg text-foreground/80">
              Upload one receipt or a whole batch. Crosscheck reads the vendor, date, items and totals. Then it checks the
              numbers and <span className="mark">flags anything it is not sure about</span>. You only look at those.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button size="lg" className="h-11 px-5 text-[15px]" asChild><Link href="/signup">Get started</Link></Button>
              <Button size="lg" variant="outline" className="h-11 px-5 text-[15px]" asChild><a href="#checks">See what it checks</a></Button>
            </div>
            <p className="mt-4 text-sm text-muted-foreground">Sign up with email or Google</p>
          </div>

          <div className="grid items-start sm:grid-cols-[1fr_minmax(0,250px)]" aria-label="A photographed receipt and the checks run on it">
            <div className="aspect-[3/4] -rotate-2 overflow-hidden rounded-xl shadow-[0_18px_40px_-18px_rgba(17,24,39,0.45)]">
              <Image src="/sample-receipt.jpg" alt="Photo of a Taco Bell receipt dated 9/1/2016, total 7.61" width={750} height={1000}
                className="size-full object-cover object-[20%_40%]" priority />
            </div>
            <div
              role="img"
              aria-label="Checks on this receipt: the lines add up to the 6.98 subtotal, 6.98 plus 0.63 tax equals the 7.61 total, and the date 9/1/2016 needs confirming"
              className="tape tape-print relative mx-6 -mt-24 rotate-[1.5deg] font-mono text-[13px] leading-[1.9] sm:mx-0 sm:mt-12 sm:-ml-10"
            >
              <p style={{ "--i": 0 } as React.CSSProperties} className="mb-2 border-b border-dashed pb-2 text-center text-[11px] tracking-[0.12em] text-muted-foreground">TACO BELL 017314</p>
              {TAPE.map(([left, right, kind], i) => (
                <p key={left} style={{ "--i": i + 1 } as React.CSSProperties}
                  className={cn("flex justify-between gap-3", kind === "flag" && "-mx-2 bg-[#ffe14d] px-2 text-[#111827]")}>
                  <span>{left}</span>
                  <span>{right}{kind === "ok" && <b className="ml-1 text-ok">✓</b>}</span>
                </p>
              ))}
              <p style={{ "--i": TAPE.length + 1 } as React.CSSProperties} className="mt-1.5 font-sans text-xs leading-snug text-muted-foreground">
                Could be 1 Sep or 9 Jan. Sent to review.
              </p>
            </div>
          </div>
          </div>
        </section>

        <section id="who" className="border-t bg-background px-6 py-22">
          <div className="mx-auto max-w-6xl">
            <h2 className="display text-[clamp(30px,3.6vw,44px)]">For the bills that come in</h2>
            <p className="mt-4 max-w-2xl text-lg text-foreground/75">
              Your till knows what you sell. But the bills you receive still get typed in by hand.
            </p>
            <div className="mt-11 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
              {useCases.map(({ icon: Icon, title, docs, text }) => (
                <div key={title} className="flex flex-col rounded-xl border bg-card p-6 shadow-xs">
                  <span className="mb-4 grid size-10 place-items-center rounded-lg bg-accent text-primary">
                    <Icon className="size-5" aria-hidden />
                  </span>
                  <h3 className="font-semibold">{title}</h3>
                  <p className="mt-1.5 mb-4 text-sm text-muted-foreground">{text}</p>
                  <p className="mt-auto border-t border-dashed pt-3 font-mono text-xs text-foreground/70">{docs}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section id="review" className="border-t px-6 py-22">
          <div className="mx-auto max-w-6xl">
            <h2 className="display text-[clamp(30px,3.6vw,44px)]">See what needs a fix</h2>
            <p className="mt-4 max-w-2xl text-lg text-foreground/75">
              The AI read the beef ribs as 1 item. The receipt says 1.89 lbs. The math check catches it and suggests 1.89. One
              click fixes it.
            </p>
            <DemoVideo name="fix" className="mt-11"
              label="Demo: a Smoke City Market receipt is flagged, the assistant explains the line math, the suggested quantity 1.89 is applied and the receipt is saved as reviewed." />
          </div>
        </section>

        <section id="assistant" className="border-t bg-background px-6 py-22">
          <div className="mx-auto grid max-w-6xl items-center gap-11 lg:grid-cols-[0.8fr_1.2fr] lg:gap-14">
            <div>
              <h2 className="display text-[clamp(30px,3.6vw,44px)]">Ask about your documents</h2>
              <p className="mt-4 text-lg text-foreground/75">
                Ask in English or Bangla. The assistant looks up your documents and explains each flag with the numbers the
                checks found. It only reads your data and never changes it.
              </p>
              <ul className="mt-8 flex flex-col items-start gap-2.5" aria-label="Example questions">
                {questions.map((q) => (
                  <li key={q} className="flex items-center gap-2.5 rounded-2xl rounded-bl-sm border bg-card px-4 py-2.5 text-sm font-medium shadow-xs">
                    <MessageCircle className="size-4 shrink-0 text-primary" aria-hidden />
                    {q}
                  </li>
                ))}
              </ul>
            </div>
            <DemoVideo name="assistant"
              label="Demo: a handwritten Bangla fruit-shop memo is open, the question এই রসিদে সমস্যা কী? is typed and the assistant answers in Bangla with the two problems the checks found." />
          </div>
        </section>

        <section id="features" className="border-t px-6 py-22">
          <div className="mx-auto max-w-6xl">
            <h2 className="display text-[clamp(30px,3.6vw,44px)]">From a pile of receipts to a clean spreadsheet</h2>
            <div className="mt-11 grid gap-5 md:grid-cols-3">
              {features.map(({ icon: Icon, title, text }) => (
                <div key={title} className="rounded-xl border bg-card p-6 shadow-xs">
                  <span className="mb-4 grid size-10 place-items-center rounded-lg bg-accent text-primary">
                    <Icon className="size-5" aria-hidden />
                  </span>
                  <h3 className="font-semibold">{title}</h3>
                  <p className="mt-1.5 text-sm text-muted-foreground">{text}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section id="checks" className="border-t bg-background px-6 py-22">
          <div className="mx-auto max-w-6xl">
            <h2 className="display text-[clamp(30px,3.6vw,44px)]">Every document is checked</h2>
            <p className="mt-4 text-lg text-foreground/75">A document that fails a check goes to your review list.</p>
            <ul className="mt-11 grid gap-3 md:grid-cols-3">
              {checks.map(([title, text]) => (
                <li key={title} className="flex gap-3 rounded-xl border bg-card p-4">
                  <span className="grid size-5.5 shrink-0 place-items-center rounded-full bg-ok-soft text-xs font-bold text-ok" aria-hidden>
                    ✓
                  </span>
                  <div>
                    <p className="font-medium">{title}</p>
                    <p className="text-sm text-muted-foreground">{text}</p>
                  </div>
                </li>
              ))}
            </ul>
            <p className="mt-6 text-foreground/75">
              When a check fails, a second AI model can read the document again and suggest fixes. Nothing changes until you choose.
            </p>
          </div>
        </section>

        <section id="privacy" className="border-t px-6 py-22">
          <div className="mx-auto max-w-6xl">
            <h2 className="display text-[clamp(30px,3.6vw,44px)]">Privacy</h2>
            <div className="mt-11 grid gap-5 md:grid-cols-3">
              {privacy.map(({ icon: Icon, title, text }) => (
                <div key={title} className="rounded-xl border bg-card p-6 shadow-xs">
                  <span className="mb-4 grid size-10 place-items-center rounded-lg bg-accent text-primary">
                    <Icon className="size-5" aria-hidden />
                  </span>
                  <h3 className="font-semibold">{title}</h3>
                  <p className="mt-1.5 text-sm text-muted-foreground">{text}</p>
                </div>
              ))}
            </div>
            <Link href="/privacy" className="mt-6 inline-block text-sm font-medium text-primary underline">Read the privacy page</Link>
          </div>
        </section>

        <section className="border-t bg-background px-6 pt-12 pb-20">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-6 rounded-2xl bg-foreground p-8 text-white dark:border dark:bg-card md:p-12">
            <div>
              <h2 className="display text-[clamp(30px,3.6vw,44px)]">Try it with a sample receipt</h2>
              <p className="mt-1.5 text-white/75">Sign up free. Sample receipts are ready to try.</p>
            </div>
            <Button size="lg" variant="secondary" className="h-11 px-5 text-[15px]" asChild><Link href="/signup">Try the demo</Link></Button>
          </div>
        </section>
      </main>

      <footer className="mx-auto flex max-w-6xl flex-wrap justify-between gap-3 border-t px-6 pt-6 pb-10 text-sm text-muted-foreground">
        <span>© 2026 Crosscheck · <Link className="underline" href="/privacy">Privacy</Link></span>
        <span>
          Built by Fahim Faiyaz · <a className="underline" href="https://www.upwork.com/freelancers/~01958224446d5f1b49">Upwork</a> ·{" "}
          <a className="underline" href="https://www.fiverr.com/fahimfaiyaz325">Fiverr</a> ·{" "}
          <a className="underline" href="https://github.com/07fahim">GitHub</a>
        </span>
      </footer>
    </div>
  );
}
