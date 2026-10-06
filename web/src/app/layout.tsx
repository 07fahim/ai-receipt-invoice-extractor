import type { Metadata } from "next";
import { Anybody, Inter, Martian_Mono } from "next/font/google";
import { Toaster } from "@/components/ui/sonner";
import "./globals.css";

const inter = Inter({ variable: "--font-sans", subsets: ["latin"] });
// wide display face for the app name and landing headlines (width axis for the stretched look)
const anybody = Anybody({ variable: "--font-display", subsets: ["latin"], axes: ["wdth"] });
const martian = Martian_Mono({ variable: "--font-mono", subsets: ["latin"] }); // receipt figures on the landing page

export const metadata: Metadata = {
  title: "Crosscheck: receipt and invoice data extraction",
  description:
    "Upload receipts and invoices. Crosscheck reads them and checks the numbers. Only unsure ones go to review.",
};

// Runs before the page paints: the saved choice, or the system setting, so there is no light flash.
const THEME = `try{var t=localStorage.getItem("theme");document.documentElement.classList.toggle("dark",t?t==="dark":matchMedia("(prefers-color-scheme: dark)").matches)}catch(e){}`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${inter.variable} ${anybody.variable} ${martian.variable} h-full antialiased`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME }} />
      </head>
      <body className="min-h-full flex flex-col">
        {children}
        <Toaster />
      </body>
    </html>
  );
}
