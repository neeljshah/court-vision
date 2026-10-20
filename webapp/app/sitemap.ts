// Build-time sitemap for the unified site. Static export emits /court-vision/sitemap.xml.
// Lists every kept section route plus the search index, research and paper pages; drops
// every retired route (lib/redirects.ts: stub pages and retired dynamic families) and any
// root whose page.tsx does not exist in this build. URLs are absolute (origin + basePath).
import type { MetadataRoute } from "next";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { getResearchAnalyses } from "@/lib/analytics/researchData";
import { loadPapers } from "@/lib/analytics/papers.server";
import { resolveRedirect } from "@/lib/redirects";

export const dynamic = "force-static";

const ORIGIN = process.env.NEXT_PUBLIC_SITE_URL || "https://neeljshah.github.io";
const BASE = process.env.NEXT_PUBLIC_BASE_PATH || "";

// Section roots in nav order: Today, Desk, Calibration, Research, Evidence, About.
const ROOTS = [
  "/", "/games",
  "/desk", "/desk/health", "/paper-trading",
  "/analytics/calibration", "/analytics/state-reliability", "/analytics/forecaster", "/analytics/compare",
  "/analytics/score-decomposition", "/analytics/residual-anatomy", "/analytics/observation-dependence",
  "/analytics/cross-sport-comparability", "/analytics/state-contrasts",
  "/analytics/papers", "/analytics/findings", "/analytics/novel", "/analytics/lab", "/analytics/players",
  "/analytics/browse", "/analytics/pitch-sequencing", "/analytics/blowout-timing", "/analytics/count-context",
  "/evidence", "/evidence/retractions", "/receipts",
  "/about", "/how-it-works", "/methodology",
];

/** True when a static page.tsx backs this route in either route group. */
function exists(route: string): boolean {
  const rel = route === "/" ? "" : route.slice(1);
  return ["(terminal)", "(analytics)"].some((g) => existsSync(join(process.cwd(), "app", g, rel, "page.tsx")));
}

/** Kept = not a redirect stub and not inside a retired dynamic family. */
const isKept = (h: string) => resolveRedirect(h) === null;

export default function sitemap(): MetadataRoute.Sitemap {
  let hrefs: string[] = [];
  try {
    const raw = readFileSync(join(process.cwd(), "public", "data", "showcase", "search_records.json"), "utf-8");
    hrefs = (JSON.parse(raw).records as Array<{ href: string }>).map((r) => r.href.replace(/\/+$/, ""));
  } catch {
    hrefs = []; // missing index: still emit the section roots
  }
  const research = getResearchAnalyses().map((a) => `/analytics/research/${a.id}`);
  const papers = loadPapers().map((p) => `/analytics/papers/${p.slug}`);
  const seen = new Set<string>();
  const urls: MetadataRoute.Sitemap = [];
  for (const h of [...ROOTS.filter(exists), ...hrefs, ...research, ...papers]) {
    if (seen.has(h) || !isKept(h)) continue;
    seen.add(h);
    urls.push({
      // trailingSlash: true -> the canonical exported page ends in "/".
      url: `${ORIGIN}${BASE}${h === "/" ? "/" : `${h}/`}`,
      changeFrequency: "weekly",
      priority: h === "/" ? 1 : ROOTS.includes(h) ? 0.8 : 0.6,
    });
  }
  return urls;
}
