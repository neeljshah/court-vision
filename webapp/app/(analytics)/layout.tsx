// Analytics product (Product 2) OWN root layout -- DESIGN_ANALYTICS Sec. 13.
// A separate route-group root: it owns its <html>, fonts, theme-init, and tokens
// with zero CSS bleed from the terminal (globals.css is never imported here). URLs
// are unchanged; pages live at app/(analytics)/analytics/* -> /analytics/*.
import "./analytics.css";

import type { Metadata } from "next";
import type { ReactNode } from "react";
import Link from "next/link";
import { analyticsFontVars } from "@/lib/analytics/fonts";
import { CommandPalette } from "@/components/analytics/CommandPalette";
import { PaletteTrigger } from "@/components/analytics/PaletteTrigger";

// Static-export builds serve at basePath /court-vision; next/font + <Link> auto-
// prefix, but the metadata icon URLs do NOT (same landmine as the terminal layout).
const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH || "";

// Social scrapers need ABSOLUTE og:image URLs. The public export is the GitHub Pages
// project site (neeljshah/court-vision -- see next.config.mjs); resolve card images
// against that origin, overridable with NEXT_PUBLIC_SITE_URL for any other host.
const SITE_ORIGIN = process.env.NEXT_PUBLIC_SITE_URL || "https://neeljshah.github.io";
const SITE_DESC =
  "Honestly-measured sports analytics across basketball, baseball, soccer, and tennis. Every number wears its receipt; no dollar edge is claimed.";
// Product 2 uses the LIGHT brand lockup for its social card (the terminal keeps its
// own marks). BASE_PATH-prefixed so it resolves under /court-vision in the export.
const OG_IMAGE = `${BASE_PATH}/brand/logo-on-light.png`;

// Pre-paint theme init: set data-theme from the analytics-scoped key before first
// paint so there is no flash of wrong theme. Default LIGHT (the product default);
// dark only if the user has explicitly chosen it here. Independent of the terminal.
const THEME_INIT = `(function(){try{var t=localStorage.getItem('cv-analytics-theme');document.documentElement.setAttribute('data-theme',t==='dark'?'dark':'light');}catch(e){}})();`;

// Post-hydration chrome: wire the theme toggle + mark the active nav pillar from the
// current path. Vanilla JS keeps the root layout a server component (no client file,
// no bundle) -- both are progressive enhancements over server-rendered links.
const CHROME_JS = `(function(){var r=document.documentElement;var b=document.getElementById('a-theme-toggle');if(b){b.addEventListener('click',function(){var n=r.getAttribute('data-theme')==='dark'?'light':'dark';r.setAttribute('data-theme',n);try{localStorage.setItem('cv-analytics-theme',n);}catch(e){}});}var p=location.pathname.replace(/^\\/court-vision/,'').replace(/\\/+$/,'');if(p==='')p='/';var L=document.querySelectorAll('a[data-nav]');for(var i=0;i<L.length;i++){var h=L[i].getAttribute('data-nav');var on=h==='/analytics'?p==='/analytics':(p===h||p.indexOf(h+'/')===0);if(on)L[i].classList.add('active');}})();`;

export const metadata: Metadata = {
  metadataBase: new URL(SITE_ORIGIN),
  title: {
    template: "%s | CourtVision Analytics",
    default: "CourtVision Analytics",
  },
  description: SITE_DESC,
  icons: {
    icon: [
      { url: `${BASE_PATH}/brand/favicon.ico`, sizes: "any" },
      { url: `${BASE_PATH}/brand/favicon-32.png`, sizes: "32x32", type: "image/png" },
      { url: `${BASE_PATH}/brand/favicon-192.png`, sizes: "192x192", type: "image/png" },
      { url: `${BASE_PATH}/brand/favicon-512.png`, sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: `${BASE_PATH}/brand/apple-touch-icon.png` }],
  },
  openGraph: {
    type: "website",
    siteName: "CourtVision Analytics",
    title: "CourtVision Analytics",
    description: SITE_DESC,
    images: [{ url: OG_IMAGE, width: 1218, height: 1266, alt: "CourtVision Analytics" }],
  },
  twitter: {
    // The share image is the brand lockup (near-square, ~1218x1266). A
    // summary_large_image card renders a ~1.91:1 landscape frame that center-crops
    // the wordmark; "summary" shows a square thumbnail the logo actually fits.
    // (A purpose-built 1200x630 card would let this go back to large_image.)
    card: "summary",
    title: "CourtVision Analytics",
    description: SITE_DESC,
    images: [OG_IMAGE],
  },
};

// Product pillars (IA Sec. 4) + the two flagship prediction surfaces from the
// NIGHT_PLAN elevated goal (Forecaster, The Loop) -- predictions are the crown.
// Hrefs point at the routes that actually ship: Explore=browse, Entities=players.
// The old Mechanisms + Findings pillars are folded into The Loop (which renders the
// mechanism ledger + graveyard + honesty exhibit); About / Explainers / Retractions
// are reachable from the footer secondary links below.
const PILLARS: Array<{ href: string; label: string }> = [
  { href: "/analytics", label: "Home" },
  { href: "/analytics/forecaster", label: "Forecaster" },
  { href: "/analytics/the-loop", label: "The Loop" },
  { href: "/analytics/novel", label: "Novel Stats" },
  { href: "/analytics/browse", label: "Explore" },
  { href: "/analytics/players", label: "Entities" },
  { href: "/analytics/ask", label: "Ask Scout" },
];

// Footer secondary links -- keep About / Explainers / Retractions reachable from
// every page (they are not top-nav pillars but must not be orphaned URLs).
const FOOT_LINKS: Array<{ href: string; label: string }> = [
  { href: "/analytics/about", label: "About" },
  { href: "/analytics/explainers", label: "Explainers" },
  { href: "/analytics/findings", label: "Findings" },
];

export default function AnalyticsRootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" data-theme="light" className={analyticsFontVars} suppressHydrationWarning>
      <head>
        {/* eslint-disable-next-line react/no-danger */}
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT }} />
      </head>
      <body>
        <a href="#analytics-main" className="a-skip">Skip to content</a>
        <nav className="a-nav" aria-label="Analytics">
          <div className="wrap a-navrow">
            <Link href="/analytics" className="a-lockup" aria-label="CourtVision Analytics home">
              <span className="a-mark" aria-hidden="true">
                <span>&#9650;</span>
              </span>
              <span>
                <span className="a-name">CourtVision</span>{" "}
                <span className="a-kicker">ANALYTICS</span>
              </span>
            </Link>
            <div className="navlinks">
              {PILLARS.map((p) => (
                <Link key={p.href} href={p.href} data-nav={p.href}>
                  {p.label}
                </Link>
              ))}
            </div>
            <PaletteTrigger />
            <button id="a-theme-toggle" className="a-theme" type="button" aria-label="Toggle light or dark theme">
              <svg className="sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                <circle cx="12" cy="12" r="4" />
                <path strokeLinecap="round" d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M19.1 4.9L17 7M7 17l-2.1 2.1" />
              </svg>
              <svg className="moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M20 14.5A8 8 0 0 1 9.5 4a7 7 0 1 0 10.5 10.5z" />
              </svg>
            </button>
          </div>
        </nav>

        <main id="analytics-main">{children}</main>

        <footer className="a-footer">
          <div className="wrap">
            <div className="a-foot-top">
              <span className="a-foot-mark" aria-hidden="true">
                <span>&#9650;</span>
              </span>
              <span className="a-foot-name">CourtVision Analytics</span>
            </div>
            <p className="a-honesty">
              <span className="k">The honest rail.</span>{" "}
              The market is efficient; we aim to match the devigged close within noise. No
              dollar edge is claimed, anywhere. Every number links to the artifact that
              produced it, and the retracted figures live only inside their retraction.
            </p>
            <p className="a-meta">
              static snapshot &middot; no live data &middot; edge_claimed: false
            </p>
            {/* Primary onward nav from the foot of long pages: the mobile top nav
                is non-sticky by design (it scrolls away), so a reader at the bottom
                needs the six pillars here to jump on without scrolling back up. */}
            <nav className="a-foot-links a-foot-pillars" aria-label="Sections">
              {PILLARS.map((p) => (
                <Link key={p.href} href={p.href}>
                  {p.label}
                </Link>
              ))}
            </nav>
            <nav className="a-foot-links" aria-label="Secondary">
              {FOOT_LINKS.map((l) => (
                <Link key={l.href} href={l.href}>
                  {l.label}
                </Link>
              ))}
            </nav>
            {/* Cross-product jump: leaves the Reading Room for the dark quant
                terminal (own theme, full reload). The up-right glyph marks it as
                leaving this product, not in-product navigation. */}
            <Link href="/" className="a-xlink" target="_blank" rel="noopener">
              Looking for the live quant terminal? Open CourtVision Terminal &#8599;
            </Link>
          </div>
        </footer>

        {/* eslint-disable-next-line react/no-danger */}
        <script dangerouslySetInnerHTML={{ __html: CHROME_JS }} />
        <CommandPalette />
      </body>
    </html>
  );
}
