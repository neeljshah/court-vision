// Build-time sitemap for the public analytics site. Static export emits this as
// /court-vision/sitemap.xml. Includes the public search index plus primary hubs.
// URLs are absolute (origin + basePath), because a project-site sitemap under a
// subpath must spell out the full https URL for crawlers to resolve it.
import type { MetadataRoute } from "next";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { getResearchAnalyses } from "@/lib/analytics/researchData";

export const dynamic = "force-static";

const ORIGIN = process.env.NEXT_PUBLIC_SITE_URL || "https://neeljshah.github.io";
const BASE = process.env.NEXT_PUBLIC_BASE_PATH || "";

export default function sitemap(): MetadataRoute.Sitemap {
  let hrefs: string[] = [];
  try {
    const raw = readFileSync(join(process.cwd(), "public", "data", "showcase", "search_records.json"), "utf-8");
    hrefs = (JSON.parse(raw).records as Array<{ href: string }>).map((r) => r.href);
  } catch {
    // Missing index -> still emit the flagship roots rather than an empty sitemap.
    hrefs = [];
  }
  // The home + hub roots always belong in, even if the index failed to load.
  const roots = ["/analytics", "/analytics/ask", "/analytics/lab", "/analytics/compare", "/analytics/evidence", "/analytics/findings", "/analytics/players", "/analytics/browse", "/analytics/calibration", "/analytics/state-reliability", "/analytics/pitch-sequencing", "/analytics/score-decomposition", "/analytics/observation-dependence", "/analytics/residual-anatomy", "/analytics/blowout-timing", "/analytics/state-contrasts", "/analytics/cross-sport-comparability"];
  const seen = new Set<string>();
  const urls: MetadataRoute.Sitemap = [];
  const research = getResearchAnalyses().map(a => `/analytics/research/${a.id}`);
  for (const h of [...roots, ...hrefs, ...research]) {
    if (seen.has(h)) continue;
    seen.add(h);
    // next.config has trailingSlash:true, so the canonical exported page is
    // /analytics/ (with slash). Emit the slashed form so crawlers index the
    // canonical URL directly instead of following a Pages redirect.
    urls.push({
      url: `${ORIGIN}${BASE}${h}/`,
      changeFrequency: "weekly",
      priority: h === "/analytics" ? 1 : h.startsWith("/analytics/findings") ? 0.8 : 0.6,
    });
  }
  return urls;
}
