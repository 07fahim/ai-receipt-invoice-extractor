import { redirect } from "next/navigation";
import { AppNav } from "@/components/app-nav";
import { AssistantPanel } from "@/components/assistant-panel";
import { createClient } from "@/lib/supabase/server";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const { data } = await (await createClient()).auth.getClaims();
  if (!data?.claims) redirect("/login");
  return (
    <div className="grid min-h-screen md:grid-cols-[232px_1fr]">
      <AppNav email={String(data.claims.email ?? "")} />
      <main className="min-w-0 px-4 pt-5 pb-24 md:px-8 md:pt-6 md:pb-12">{children}</main>
      <AssistantPanel />
    </div>
  );
}
