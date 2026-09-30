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
    "Upload receipts and invoices. Crosscheck extracts the vendor, dates, line items and totals, checks the numbers, and sends only uncertain documents to review.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${inter.variable} ${anybody.variable} ${martian.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col">
        {children}
        <Toaster />
      </body>
    </html>
  );
}
