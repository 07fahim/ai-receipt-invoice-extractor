import type { Metadata } from "next";
import Link from "next/link";
import { Logo } from "@/components/logo";

export const metadata: Metadata = { title: "Privacy · Crosscheck" };

// Plain privacy note. Keep it true to the code. Update it when a service is added or the AI plan changes.
const sections: [string, React.ReactNode][] = [
  ["Who runs Crosscheck", <>
    <p>Crosscheck is a demo. Fahim Faiyaz builds and runs it from Bangladesh. Please upload sample documents only.</p>
  </>],
  ["What is stored", <>
    <ul className="list-disc space-y-1.5 pl-5">
      <li>Your email and a hashed password. With Google sign-in, also your name and picture.</li>
      <li>Your files and the data read from them.</li>
      <li>Your corrections and vendor date settings.</li>
      <li>The AI&apos;s first reading of each file. I compare it with your corrections to measure how often the AI is wrong.</li>
      <li>The time of each upload. This is for the daily limit.</li>
      <li>Your webhook address and its secret, if you add one. Both are encrypted.</li>
    </ul>
    <p>No ads. No tracking. Cookies only keep you signed in.</p>
  </>],
  ["Where it is stored", <>
    <p>Supabase stores it in Mumbai, India. Only you can see your documents.</p>
  </>],
  ["Who else sees your documents", <>
    <ul className="list-disc space-y-1.5 pl-5">
      <li>
        <b>Google Gemini</b> reads each file. This demo uses the free plan. On it, Google may use files to improve its AI.
        People at Google may also see them.
      </li>
      <li><b>Gmail</b> sends the sign-up and reset emails.</li>
      <li><b>Supabase</b> stores the data and handles sign-in.</li>
      <li><b>Render</b> runs the server that receives your files, in Singapore. It does not keep them.</li>
      <li><b>Vercel</b> hosts this website. Your files do not pass through it.</li>
      <li><b>Your webhook</b>, if you add one, gets the data read from each file. Not the file itself.</li>
    </ul>
    <p>Nothing is sold or shared with anyone else.</p>
  </>],
  ["How long it is kept", <>
    <p>Until you delete it. Deleting a document removes it right away. Deleting your account removes everything.</p>
  </>],
  ["Your rights", <>
    <p>
      You can view, fix, export and delete your data in the app. For anything else, contact me on{" "}
      <a className="underline" href="https://github.com/07fahim">GitHub</a>.
    </p>
  </>],
  ["The law", <>
    <p>Bangladesh&apos;s Personal Data Protection Act 2026 is new. Its rules are still coming into force. This page is not legal advice.</p>
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
        <p className="mt-2 text-sm text-muted-foreground">Last updated 2 October 2026</p>
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
