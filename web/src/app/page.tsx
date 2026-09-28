import Image from "next/image";
import Link from "next/link";
import { ClipboardCheck, Download, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Logo } from "@/components/logo";
import { cn } from "@/lib/utils";

const features = [
  { icon: Upload, title: "Upload in batches", text: "Drop up to 20 photos or PDFs at once. Most are done in about five seconds." },
  { icon: ClipboardCheck, title: "Review only what needs it", text: "Flagged fields are shown next to the original, with the reason." },
  { icon: Download, title: "Export anywhere", text: "Download CSV, Excel or a QuickBooks bill import, or send rows to Google Sheets." },
];

const checks = [
  ["Line items match the subtotal", "After any line discounts"],
  ["Totals add up", "Subtotal + tax + service − discount"],
  ["Each line adds up", "Quantity × unit price"],
  ["Dates are valid", "Unclear dates like 05/11 go to review"],
  ["Currency is valid", "USD, BDT, INR and more"],
  ["Nothing is missing", "Total and line items present"],
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
  "Only you can see the documents you upload.",
  "Delete any document, or your whole account, at any time.",
  "Documents are processed by a third-party AI service. Please upload sample documents while this is a demo.",
];

export default function Home() {
  return (
    <div className="bg-card">
      <header className="sticky top-0 z-10 border-b bg-card/85 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
          <Logo />
          <nav className="flex items-center gap-7 text-sm font-medium text-foreground/80">
            <a href="#features" className="hidden hover:text-foreground md:block">Features</a>
            <a href="#checks" className="hidden hover:text-foreground md:block">Checks</a>
            <a href="#privacy" className="hidden hover:text-foreground md:block">Privacy</a>
            <Link href="/login" className="hover:text-foreground">Log in</Link>
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
              Upload receipts and invoices, one or a whole batch. Crosscheck reads the vendor, dates, line items and totals,
              checks that the numbers add up, and <span className="mark">highlights anything it is not sure about</span> so you
              only look at those.
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
                  className={cn("flex justify-between gap-3", kind === "flag" && "-mx-2 bg-[#ffe14d] px-2")}>
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

        <section id="features" className="border-t bg-background px-6 py-22">
          <div className="mx-auto max-w-6xl">
            <h2 className="display text-[clamp(30px,3.6vw,44px)]">From a pile of receipts to a clean spreadsheet</h2>
            <p className="mt-4 max-w-2xl text-lg text-foreground/75">
              For bookkeepers and small businesses who still type receipts and invoices in by hand.
            </p>
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

        <section id="checks" className="px-6 py-22">
          <div className="mx-auto max-w-6xl">
            <h2 className="display text-[clamp(30px,3.6vw,44px)]">Every document is checked</h2>
            <p className="mt-4 text-lg text-foreground/75">A document that fails a check goes to your review list.</p>
            <ul className="mt-11 grid gap-3 md:grid-cols-3">
              {checks.map(([title, text]) => (
                <li key={title} className="flex gap-3 rounded-xl border p-4">
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
          </div>
        </section>

        <section id="privacy" className="border-t bg-background px-6 py-22">
          <div className="mx-auto grid max-w-6xl gap-5 md:grid-cols-[1fr_1.4fr] md:gap-12">
            <h2 className="display text-[clamp(30px,3.6vw,44px)]">Privacy</h2>
            <ul className="divide-y">
              {privacy.map((p) => (
                <li key={p} className="py-3 text-foreground/85 first:pt-0">{p}</li>
              ))}
            </ul>
          </div>
        </section>

        <section className="px-6 py-22">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-6 rounded-2xl bg-foreground p-8 text-white md:p-12">
            <div>
              <h2 className="display text-[clamp(30px,3.6vw,44px)]">Try it with a sample receipt</h2>
              <p className="mt-1.5 text-white/75">Results in seconds.</p>
            </div>
            <Button size="lg" variant="secondary" className="h-11 px-5 text-[15px]" asChild><Link href="/signup">Get started</Link></Button>
          </div>
        </section>
      </main>

      <footer className="mx-auto flex max-w-6xl flex-wrap justify-between gap-3 border-t px-6 pt-6 pb-10 text-sm text-muted-foreground">
        <span>© 2026 Crosscheck</span>
        <span>
          Built by Fahim Faiyaz · <a className="underline" href="https://www.upwork.com/freelancers/~01958224446d5f1b49">Upwork</a> ·{" "}
          <a className="underline" href="https://www.fiverr.com/fahimfaiyaz325">Fiverr</a> ·{" "}
          <a className="underline" href="https://github.com/07fahim">GitHub</a>
        </span>
      </footer>
    </div>
  );
}
