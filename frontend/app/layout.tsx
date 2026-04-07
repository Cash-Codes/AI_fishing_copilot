// layout.tsx — Root layout: wraps every page in the app.
// Think of this like the outer shell that never changes while you navigate.

import type { Metadata } from "next";
import "./globals.css";

// Metadata shown in the browser tab and search results
export const metadata: Metadata = {
  title: "AI Fishing Copilot",
  description: "Find the best time and place to fish near you.",
};

// RootLayout receives the current page as `children` and renders it inside
// the HTML shell. Required by Next.js App Router.
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        {/* The page content (e.g. the homepage) is rendered here */}
        {children}
      </body>
    </html>
  );
}
