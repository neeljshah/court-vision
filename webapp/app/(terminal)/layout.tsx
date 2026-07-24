import "../globals.css";

import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { Metadata } from "next";
import type { ReactNode } from "react";
import { AppShell, THEME_INIT_SCRIPT } from "@/components/AppShell";
import { isSnapshotMode } from "@/lib/fetchHonest";

// Demo banner: static-export builds serve a frozen sample snapshot, not live
// data -- read generated_at straight off the baked manifest (build-time only,
// server component) so the honesty rail is never a lie. ponytail: omit the
// timestamp rather than fail the build if the manifest is missing/unreadable.
function demoGeneratedAt(): string | null {
  if (!isSnapshotMode) return null;
  try {
    const manifest = JSON.parse(
      readFileSync(join(process.cwd(), "public/demo-data/manifest.json"), "utf-8"),
    ) as { generated_at?: string };
    return manifest.generated_at ?? null;
  } catch {
    return null;
  }
}

// Next's next/image + metadata icons do NOT auto-prefix basePath when
// images.unoptimized is true (export mode) -- same landmine as
// lib/fetchHonest.ts's BASE_PATH, so prefix by hand here too.
const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH || "";

export const metadata: Metadata = {
  title: {
    template: "%s | CourtVision",
    default: "CourtVision",
  },
  description:
    "Real-time NBA in-play intelligence. Calibrated predictions -- paper-only, no dollar edge claimed.",
  icons: {
    icon: [
      { url: `${BASE_PATH}/brand/favicon.ico`, sizes: "any" },
      { url: `${BASE_PATH}/brand/favicon-32.png`, sizes: "32x32", type: "image/png" },
      { url: `${BASE_PATH}/brand/icon-192.png`, sizes: "192x192", type: "image/png" },
      { url: `${BASE_PATH}/brand/icon-512.png`, sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: `${BASE_PATH}/brand/apple-touch-icon.png` }],
  },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  const generatedAt = demoGeneratedAt();
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
        {isSnapshotMode && (
          <div className="border-b border-warning bg-warning/10 px-4 py-1 text-center font-mono text-[11px] uppercase tracking-wide text-warning">
            Demo -- read-only snapshot of the live system
            {generatedAt ? ` as of ${generatedAt}` : ""}; no live data, paper
            units only.
          </div>
        )}
        {/* AppShell is a client component: provides Nav, footer, theme toggle. */}
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
