// app/layout.tsx -- the ONE root layout: <html>/<body>, the one theme init, metadata
// (title template "%s | CourtVision"), the snapshot banner, the skip link, the search
// palette and the cross-group navigation guard. Each route group layout adds its own
// stylesheet plus the shared SiteHeader / Breadcrumbs / SiteFooter. No stylesheet is
// imported here, so neither group's CSS reaches the other (see CrossGroupNav).
import type { Metadata } from "next";
import type { ReactNode } from "react";
import { analyticsFontVars } from "@/lib/analytics/fonts";
import { CommandPalette } from "@/components/analytics/CommandPalette";
import { CrossGroupNav } from "@/components/shell/CrossGroupNav";
import { THEME_INIT_SCRIPT } from "@/components/shell/theme";
import { snapshotDates, snapshotLine } from "@/components/shell/snapshot.server";
import { SITE_DESCRIPTION as DESC } from "@/lib/seo/meta";
import s from "@/components/shell/shell.module.css";

// next/image + metadata icons do NOT auto-prefix basePath in export mode; prefix by hand.
const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH || "";
// Social scrapers need absolute og:image URLs (GitHub Pages project site by default).
const SITE_ORIGIN = process.env.NEXT_PUBLIC_SITE_URL || "https://neeljshah.github.io";
const OG_IMAGE = `${BASE_PATH}/brand/og-analytics.png`;
// Per-page canonical / og:url / descriptions come from lib/seo/meta pageMeta; this is the default.

export const metadata: Metadata = {
  metadataBase: new URL(SITE_ORIGIN),
  manifest: `${BASE_PATH}/manifest.webmanifest`,
  title: { template: "%s | CourtVision", default: "CourtVision" },
  description: DESC,
  icons: {
    icon: [
      { url: `${BASE_PATH}/brand/favicon.ico`, sizes: "any" },
      { url: `${BASE_PATH}/brand/favicon-32.png`, sizes: "32x32", type: "image/png" },
      { url: `${BASE_PATH}/brand/icon-192.png`, sizes: "192x192", type: "image/png" },
      { url: `${BASE_PATH}/brand/icon-512.png`, sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: `${BASE_PATH}/brand/apple-touch-icon.png` }],
  },
  openGraph: {
    type: "website",
    siteName: "CourtVision",
    title: "CourtVision",
    description: DESC,
    images: [{ url: OG_IMAGE, width: 1200, height: 630, alt: "CourtVision: a calibrated forecaster and its public scorecard." }],
  },
  twitter: { card: "summary_large_image", title: "CourtVision", description: DESC, images: [OG_IMAGE] },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  const asOf = snapshotLine(snapshotDates());
  return (
    <html lang="en" className={analyticsFontVars} suppressHydrationWarning>
      <head>
        {/* Runs before paint: sets html.dark + data-theme from the stored choice or the OS. */}
        {/* eslint-disable-next-line react/no-danger */}
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body>
        <a href="#main-content" className={s.skip}>Skip to main content</a>
        {asOf && (
          <div className={s.banner} role="region" aria-label="Snapshot notice">
            Read-only snapshot: {asOf}. No live data; paper units only.
          </div>
        )}
        {children}
        <CommandPalette />
        <CrossGroupNav />
      </body>
    </html>
  );
}
