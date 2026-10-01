"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/status-badge";
import { getJSON, money, type DocumentRow } from "@/lib/api";

type Sum = { currency: string | null; total: number; n: number };
type Stats = {
  documents: number;
  by_status: Record<string, number>;
  spend_by_currency: Sum[];
  tax_by_currency: Sum[];
  top_vendors: (Sum & { vendor: string })[];
  by_month: (Sum & { month: string })[];
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const label = (month: string) => `${MONTHS[Number(month.slice(5, 7)) - 1]} ${month.slice(2, 4)}`;
const NO_CURRENCY = "No currency";
const ym = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
// first day of each range, in the user's own time zone; "" = all time
const RANGES: Record<string, () => string> = {
  "All time": () => "",
  "This month": () => `${ym(new Date())}-01`,
  "Last 3 months": () => { const d = new Date(); d.setDate(1); d.setMonth(d.getMonth() - 2); return `${ym(d)}-01`; },
  "This year": () => `${new Date().getFullYear()}-01-01`,
};

// Spend over the whole period, empty months/years as 0 so gaps show as gaps: by month up to 12 months, else by year
// (so every document in the totals is on the chart). A chosen period runs from its start to this month;
// all time runs from the first to the last document.
function spendSeries(rows: { month: string; total: number }[], from: string) {
  if (!rows.length) return { by: "month", points: [] };
  const first = from ? from.slice(0, 7) : rows[0].month;
  const lastRow = rows[rows.length - 1].month;
  const last = from && ym(new Date()) > lastRow ? ym(new Date()) : lastRow;
  const span = (Number(last.slice(0, 4)) - Number(first.slice(0, 4))) * 12 + Number(last.slice(5, 7)) - Number(first.slice(5, 7)) + 1;
  const sum = (prefix: string) => rows.filter((r) => r.month.startsWith(prefix)).reduce((t, r) => t + Number(r.total), 0);
  const points = [];
  if (span > 12) {
    for (let y = Number(first.slice(0, 4)); y <= Number(last.slice(0, 4)); y++) points.push({ label: String(y), total: sum(`${y}-`) });
    return { by: "year", points };
  }
  for (const d = new Date(Number(first.slice(0, 4)), Number(first.slice(5, 7)) - 1, 1); ym(d) <= last; d.setMonth(d.getMonth() + 1)) {
    points.push({ label: label(ym(d)), total: sum(ym(d)) });
  }
  return { by: "month", points };
}

export default function DashboardPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [recent, setRecent] = useState<DocumentRow[]>([]);
  const [currency, setCurrency] = useState<string | null>(null);
  const [range, setRange] = useState("All time");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const from = RANGES[range]();
    let current = true; // a slower answer for an earlier range must not overwrite this one
    getJSON<Stats>(from ? `/stats?date_from=${from}` : "/stats")
      .then((s) => {
        if (!current) return;
        setStats(s);
        // keep the chosen currency; otherwise start with the one that has the most documents
        const top = [...s.spend_by_currency].sort((a, b) => b.n - a.n)[0];
        setCurrency((c) => (c && (!s.spend_by_currency.length || s.spend_by_currency.some((x) => (x.currency ?? NO_CURRENCY) === c)) ? c : top ? top.currency ?? NO_CURRENCY : null));
      })
      .catch((e) => current && setError(e.message));
    return () => { current = false; };
  }, [range]);
  useEffect(() => {
    getJSON<DocumentRow[]>("/documents?limit=5").then(setRecent).catch(() => {});
  }, []);

  if (error) return <p className="text-bad">{error}</p>;
  if (!stats) return <p className="text-muted-foreground">Loading…</p>;

  if (stats.documents === 0) {
    return (
      <div className="mx-auto mt-16 max-w-md text-center">
        <h1 className="text-xl font-semibold">Your dashboard is empty</h1>
        <p className="mt-1.5 text-muted-foreground">Upload receipts or invoices to see spend by month and by vendor.</p>
        <Button asChild className="mt-5"><Link href="/app/upload">Upload documents</Link></Button>
      </div>
    );
  }

  const is = (c: string | null) => (c ?? NO_CURRENCY) === currency;
  const spend = stats.spend_by_currency.find((s) => is(s.currency));
  const others = stats.spend_by_currency.filter((s) => !is(s.currency));
  const tax = stats.tax_by_currency.find((s) => is(s.currency));
  const { by, points: months } = spendSeries(stats.by_month.filter((m) => is(m.currency)), RANGES[range]());
  const vendors = stats.top_vendors.filter((v) => is(v.currency)).slice(0, 5);
  const code = currency === NO_CURRENCY ? "" : currency ?? "";

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">Spend from passed and reviewed documents</p>
        </div>
        <div className="flex gap-2">
          <select
            aria-label="Date range"
            className="h-9 rounded-md border border-input bg-card px-2.5 text-sm"
            value={range}
            onChange={(e) => setRange(e.target.value)}
          >
            {Object.keys(RANGES).map((r) => <option key={r}>{r}</option>)}
          </select>
          {stats.spend_by_currency.length > 1 && (
            <select
              aria-label="Currency"
              className="h-9 rounded-md border border-input bg-card px-2.5 text-sm"
              value={currency ?? ""}
              onChange={(e) => setCurrency(e.target.value)}
            >
              {stats.spend_by_currency.map((s) => (
                <option key={s.currency ?? NO_CURRENCY}>{s.currency ?? NO_CURRENCY}</option>
              ))}
            </select>
          )}
          <Button asChild className="h-9"><Link href="/app/upload">Upload documents</Link></Button>
        </div>
      </div>

      <div className="mb-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi label="Total spend" value={spend ? money(spend.total) : "–"} unit={spend ? code : undefined}>
          {others.length > 0
            ? `Not included: ${others.map((o) => `${o.n} ${o.currency ?? "no-currency"}`).join(", ")} document${others.length > 1 || others[0].n > 1 ? "s" : ""}`
            : `${spend?.n ?? 0} document${spend?.n === 1 ? "" : "s"}`}
        </Kpi>
        <Kpi label="Tax / VAT paid" value={tax ? money(tax.total) : "–"} unit={tax ? code : undefined}>
          {tax ? `on ${tax.n} document${tax.n === 1 ? "" : "s"}` : spend ? "No tax printed" : "No documents"}
        </Kpi>
        <Kpi label="Needs review" value={String(stats.by_status.needs_review ?? 0)}>
          {stats.by_status.needs_review ? <Link href="/app/review" className="font-medium text-primary underline">Review now</Link> : "All clear"}
        </Kpi>
        <Kpi label="Documents" value={String(stats.documents)}>
          {(stats.by_status.passed ?? 0) + (stats.by_status.reviewed ?? 0)} checked
          {stats.by_status.failed ? <> · <Link href="/app/documents" className="font-medium text-primary underline">{stats.by_status.failed} failed</Link></> : null}
        </Kpi>
      </div>

      <div className="mb-5 grid gap-4 lg:grid-cols-[1.5fr_1fr]">
        <Card title={`Spend by ${by}`} note={`${code || "No currency"}, by issue date`}>
          {months.length ? (
            <div className="h-60" role="img" aria-label={`Spend by ${by}: ${months.map((m) => `${m.label} ${money(m.total)}`).join(", ")}`}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={months} margin={{ top: 8, right: 4, bottom: 0, left: 0 }}>
                  <CartesianGrid vertical={false} stroke="#EEF0F3" />
                  <XAxis dataKey="label" tickLine={false} axisLine={false} fontSize={12} />
                  <YAxis tickLine={false} axisLine={false} fontSize={12} width={56} tickFormatter={(v) => Number(v).toLocaleString("en-US")} />
                  <Tooltip cursor={{ fill: "#F3F4F6" }} formatter={(v) => [money(Number(v), code), "Spend"]} />
                  <Bar dataKey="total" fill="var(--primary)" radius={[4, 4, 0, 0]} maxBarSize={44} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No dated documents in this currency{range === "All time" ? " yet" : " in this period"}.</p>
          )}
        </Card>
        <Card title="Top vendors" note={code}>
          {vendors.length ? (
            <ul className="grid gap-3">
              {vendors.map((v) => (
                <li key={v.vendor} className="grid grid-cols-[1fr_auto] gap-x-3 gap-y-1 text-sm tabular-nums">
                  <span className="truncate">{v.vendor}</span>
                  <span>{money(v.total)}</span>
                  <span className="col-span-2 h-1.5 overflow-hidden rounded-full bg-[#EEF0F3]">
                    <span className="block h-full rounded-full bg-chart-2" style={{ width: `${(v.total / vendors[0].total) * 100}%` }} />
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">No vendors in this currency{range === "All time" ? " yet" : " in this period"}.</p>
          )}
        </Card>
      </div>

      <Card title="Recent documents" note={<Link href="/app/documents" className="text-primary underline">View all</Link>}>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[520px] text-sm">
            <tbody className="divide-y">
              {recent.map((r) => (
                <tr key={r.id}>
                  <td className="py-2.5 pr-3">
                    <Link href={`/app/documents/${r.id}`} className="font-medium text-primary hover:underline">{r.vendor ?? r.file_name}</Link>
                  </td>
                  <td className="py-2.5 pr-3 tabular-nums">{r.issue_date ?? "–"}</td>
                  <td className="py-2.5 pr-3 text-right tabular-nums">{money(r.total, r.currency)}</td>
                  <td className="py-2.5 text-right"><StatusBadge status={r.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function Kpi({ label, value, unit, children }: { label: string; value: string; unit?: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border bg-card px-5 py-4 shadow-xs">
      <p className="text-[13px] font-medium text-muted-foreground">{label}</p>
      <p className="mt-1.5 text-[26px] leading-tight font-semibold tabular-nums">
        {value}
        {unit && <span className="ml-1 text-sm font-medium text-muted-foreground">{unit}</span>}
      </p>
      <p className="mt-0.5 text-[13px] text-muted-foreground">{children}</p>
    </div>
  );
}

function Card({ title, note, children }: { title: string; note?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border bg-card px-5 py-4 shadow-xs">
      <h2 className="mb-4 flex items-baseline justify-between text-[15px] font-semibold">
        {title}
        {note && <span className="text-[13px] font-normal text-muted-foreground">{note}</span>}
      </h2>
      {children}
    </section>
  );
}
