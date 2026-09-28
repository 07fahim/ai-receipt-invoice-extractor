import Link from "next/link";
import { ClipboardCheck, Download, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Logo } from "@/components/logo";

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
        <section className="bg-gradient-to-b from-card to-background px-6 pt-20 text-center">
          <h1 className="mx-auto max-w-3xl text-4xl font-bold tracking-tight md:text-6xl md:leading-[1.08]">
            Turn receipts and invoices into clean, checked data
          </h1>
          <p className="mx-auto mt-5 max-w-xl text-lg text-foreground/75">
            Upload photos or PDFs. Crosscheck extracts the vendor, dates, line items and totals, checks the numbers,
            and sends only uncertain documents to review.
          </p>
          <div className="mt-8 flex justify-center gap-3">
            <Button size="lg" className="h-11 px-5 text-[15px]" asChild><Link href="/signup">Get started</Link></Button>
            <Button size="lg" variant="outline" className="h-11 px-5 text-[15px]" asChild><a href="#features">See how it works</a></Button>
          </div>
          <p className="mt-4 pb-14 text-sm text-muted-foreground">Sign up with email or Google</p>
        </section>

        <section id="features" className="border-t bg-background px-6 py-22">
          <div className="mx-auto max-w-6xl">
            <h2 className="text-3xl font-bold tracking-tight">From a pile of receipts to a clean spreadsheet</h2>
            <p className="mt-3 max-w-2xl text-lg text-foreground/75">
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
            <h2 className="text-3xl font-bold tracking-tight">Every document is checked</h2>
            <p className="mt-3 text-lg text-foreground/75">A document that fails a check goes to your review list.</p>
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
            <h2 className="text-3xl font-bold tracking-tight">Privacy</h2>
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
              <h2 className="text-3xl font-bold tracking-tight">Try it with a sample receipt</h2>
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
