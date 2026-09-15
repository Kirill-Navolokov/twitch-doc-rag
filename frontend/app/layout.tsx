import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";

import "./globals.css";

import type { Metadata } from "next";
import type { ReactNode } from "react";

const plexSans = IBM_Plex_Sans({
  variable: "--font-plex-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

const plexMono = IBM_Plex_Mono({
  variable: "--font-plex-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "Ask the Twitch docs",
  description:
    "Ask a question about the Twitch API reference and read the answer alongside the passages it was drawn from.",
};

// Typed here rather than through Next's generated LayoutProps so `tsc --noEmit` needs no build first.
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${plexSans.variable} ${plexMono.variable} h-full`}>
      <body className="font-sans h-full">{children}</body>
    </html>
  );
}
