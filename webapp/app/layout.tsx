import "./globals.css";

import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "CourtVision Live",
  description: "Real-time NBA in-play intelligence + bet ranking",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-bg-base text-slate-200">
        {children}
      </body>
    </html>
  );
}
