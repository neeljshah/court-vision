// Analytics product (Product 2) type system -- DESIGN_ANALYTICS Sec. 2.
// Loaded via next/font/google (approved override of the spec's next/font/local):
// Google auto-subsets + self-hosts the woff2 at build, so the static export ships
// no runtime font fetch. Each face exposes a CSS variable consumed by analytics.css
// (--font-fraunces / --font-franklin / --font-plex-mono). Scoped to the analytics
// route group ONLY -- the layout applies these .variable classes on its own <html>.
import { Fraunces, Libre_Franklin, IBM_Plex_Mono } from "next/font/google";

// Display serif: warm editorial headlines + hero numerals. Variable wght + opsz;
// weight is left to CSS (400/500 in the scale). tnum handled per-element in CSS.
export const fraunces = Fraunces({
  subsets: ["latin"],
  display: "swap",
  axes: ["opsz"],
  variable: "--font-fraunces",
});

// Humanist sans (NYT-Franklin lineage): all body, UI, labels, table cells.
export const franklin = Libre_Franklin({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-franklin",
});

// Mono: receipts, artifact paths, source drawers only. Static face -> weights given.
export const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  display: "swap",
  weight: ["400", "500"],
  variable: "--font-plex-mono",
});

// One class string for the analytics <html>, making all three vars global to the group.
export const analyticsFontVars = `${fraunces.variable} ${franklin.variable} ${plexMono.variable}`;
