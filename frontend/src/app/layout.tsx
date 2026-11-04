import type { Metadata } from "next";
import { Geist, Geist_Mono, Instrument_Serif } from "next/font/google";
import "./globals.css";
import "./studio.css";

import AppShell from "@/components/layout/AppShell";

// Geist for the UI, Geist Mono for identifiers (PIIDs, CLINs, clause numbers)
// and audit timestamps, Instrument Serif for display headlines. Sans and mono
// fill the existing font variables, so every component switches without edits.
const sans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
  display: "swap",
});

const mono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
  display: "swap",
});

const serif = Instrument_Serif({
  variable: "--font-dx-serif",
  subsets: ["latin"],
  weight: "400",
  style: ["normal", "italic"],
  display: "swap",
});

const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL ?? "https://dataomatix.vercel.app";
const SITE_DESCRIPTION =
  "Source-grounded extraction for federal contracts. Every field is boxed on the source page, low-confidence values route to human review, and approved data exports Oracle-ready with a full audit trail.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: "Dataomatix — Federal contract extraction you can verify",
    template: "%s · Dataomatix",
  },
  description: SITE_DESCRIPTION,
  applicationName: "Dataomatix",
  keywords: [
    "federal contract extraction",
    "FAR DFARS clause extraction",
    "document intelligence",
    "source grounding",
    "human in the loop review",
    "SF 1449 extraction",
    "CLIN and ACRN funding lines",
    "Oracle Fusion export",
  ],
  openGraph: {
    type: "website",
    url: "/",
    siteName: "Dataomatix",
    title: "Dataomatix — Federal contract extraction you can verify",
    description: SITE_DESCRIPTION,
  },
  twitter: {
    card: "summary_large_image",
    title: "Dataomatix — Federal contract extraction you can verify",
    description: SITE_DESCRIPTION,
  },
  icons: {
    icon: "/brand/dataomatix-icon.png",
    apple: "/brand/dataomatix-icon.png",
  },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${sans.variable} ${mono.variable} ${serif.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <head>
        {/* The saved theme before first paint (no light flash in dark mode). */}
        <script
          dangerouslySetInnerHTML={{
            __html: `try{if(localStorage.getItem("dx-theme")==="dark")document.documentElement.dataset.theme="dark"}catch(e){}`,
          }}
        />
      </head>
      <body className="h-full overflow-hidden" suppressHydrationWarning>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
