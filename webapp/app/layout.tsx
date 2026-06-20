import "./globals.css";

import type { Metadata } from "next";
import type { ReactNode } from "react";
import { AppShell, THEME_INIT_SCRIPT } from "@/components/AppShell";

export const metadata: Metadata = {
  title: {
    template: "%s | CourtVision",
    default: "CourtVision",
  },
  description:
    "Real-time NBA in-play intelligence. Calibrated predictions -- paper-only, no dollar edge claimed.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    // Start dark by default; the ThemeScript below will override if the user
    // has previously chosen light mode. The "dark" class here prevents FOWT
    // on first load for the majority (dark-default) of users.
    <html lang="en" className="dark" suppressHydrationWarning>
      <head>
        {/* Theme-init script runs before paint to prevent flash-of-wrong-theme. */}
        {/* eslint-disable-next-line react/no-danger */}
        <script
          dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }}
        />
      </head>
      <body className="min-h-screen bg-background text-foreground antialiased">
        {/* AppShell is a client component: provides Nav, footer, theme toggle. */}
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
