"use client";

import { Moon, Sun } from "lucide-react";
import { cn } from "@/lib/utils";

// The icon follows the .dark class through CSS, so no state is needed.
export function ThemeToggle({ className }: { className?: string }) {
  function toggle() {
    const dark = document.documentElement.classList.toggle("dark");
    localStorage.setItem("theme", dark ? "dark" : "light");
  }
  return (
    <button
      onClick={toggle}
      aria-label="Switch between light and dark theme"
      title="Light or dark theme"
      className={cn("rounded-md p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground", className)}
    >
      <Moon className="size-4 dark:hidden" />
      <Sun className="hidden size-4 dark:block" />
    </button>
  );
}
