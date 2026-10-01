import type { Metadata } from "next";
import Link from "next/link";
import { Logo } from "@/components/logo";

export const metadata: Metadata = { title: "Privacy · Crosscheck" };

// Plain-language privacy note. Keep it true to the code: update it when a service is added or the AI plan changes.
const sections: [string, React.ReactNode][] = [
  ["Who runs Crosscheck", <>
    Crosscheck is a demo built and run by one person, Fahim Faiyaz, in Bangladesh. It is not a company product.
    Please upload sample documents, not real customer or personal records.
  </>],
  ["What is stored", <>
    <ul className="list-disc space-y-1.5 pl-5">
      <li>Your account: your email address and a securely hashed password. If you sign in with Google, the name and picture on your Google account.</li>
      <li>The files you upload, and the data read from them: vendor, dates, amounts, line items and the results of the checks.</li>
      <li>Your corrections, and the date format you chose for a vendor.</li>
      <li>The time of each upload or retry, to apply the daily limit.</li>
    </ul>
    <p>There is no advertising and no analytics or tracking. The only cookies keep you signed in.</p>
  </>],
  ["Where it is stored", <>
    In a database run by Supabase, in its South Asia (Mumbai, India) region. Only you can see your documents.
  </>],
  ["Who else sees your documents", <>
    <ul className="list-disc space-y-1.5 pl-5">
      <li>
        <b>Google (Gemini AI)</b> reads each uploaded file to extract the data. This demo uses Google&apos;s free Gemini API, and on
        the free plan Google may use what is sent to improve its products, and people at Google may review it. This is the
        main reason to upload samples only.
      </li>
      <li><b>Google (Gmail)</b> sends the sign-up and password reset emails.</li>
      <li><b>Supabase</b> stores the data and handles sign-in.</li>
    </ul>
    <p>Nothing is sold or shared with anyone else.</p>
  </>],
  ["How long it is kept", <>
    Until you delete it. Deleting a document removes the file and its data. Deleting your account (on the Account page)
    removes your account and everything listed above straight away.
  </>],
  ["Your rights", <>
    You can see, correct, export (CSV or Excel) and delete your data yourself in the app. For anything else, contact me
    through <a className="underline" href="https://github.com/07fahim">GitHub</a>.
  </>],
  ["The law", <>
    Bangladesh&apos;s Personal Data Protection Act 2026 is new and its rules are still coming into force. This page explains
    plainly what happens to your data; it is not legal advice and does not claim any certification.
  </>],
];

export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-card">
      <header className="border-b">
        <div className="mx-auto flex h-16 max-w-3xl items-center justify-between px-6">
          <Logo />
          <Link href="/" className="text-sm font-medium text-foreground/80 hover:text-foreground">Home</Link>
        </div>
      </header>
      <main className="mx-auto max-w-3xl px-6 py-12">
        <h1 className="text-3xl font-semibold tracking-tight">Privacy</h1>
        <p className="mt-2 text-sm text-muted-foreground">Last updated 1 October 2026</p>
        <div className="mt-8 space-y-8">
          {sections.map(([title, body]) => (
            <section key={title}>
              <h2 className="text-lg font-semibold">{title}</h2>
              <div className="mt-2 space-y-3 leading-relaxed text-foreground/85">{body}</div>
            </section>
          ))}
        </div>
      </main>
    </div>
  );
}
