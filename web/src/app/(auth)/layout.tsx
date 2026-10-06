import { Logo } from "@/components/logo";
import { ThemeToggle } from "@/components/theme-toggle";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <main className="relative flex min-h-screen flex-col items-center justify-center gap-8 px-4 py-12">
      <ThemeToggle className="absolute top-4 right-4" />
      <Logo />
      <div className="w-full max-w-sm rounded-xl border bg-card p-7 shadow-xs">{children}</div>
    </main>
  );
}
