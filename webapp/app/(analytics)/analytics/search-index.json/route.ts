import { snapshot } from "@/lib/analytics/labHelpers";
import { getResearchAnalyses } from "@/lib/analytics/researchData";
import { loadPapers } from "@/lib/analytics/papers.server";
import { resolveRedirect } from "@/lib/redirects";
import { inspectorSearchRecords } from "@/lib/analytics/analysisDestinations";
export const dynamic = "force-static";
// Site-root pages, listed here once (the palette adds only the papers hub).
const SITE_PAGES: Array<[string, string]> = [
  ["/", "Today"], ["/games", "Games"], ["/desk", "Desk"], ["/desk/health", "Desk health"], ["/paper-trading", "Paper record"],
  ["/evidence", "Evidence"], ["/evidence/retractions", "Retraction record"], ["/receipts", "Receipts"],
  ["/about", "About"], ["/how-it-works", "How it works"], ["/methodology", "Methodology"], ["/graveyard", "Graveyard"],
];
export function GET() {
  const original = snapshot<{ records: unknown[] }>("search_records");
  const derived = getResearchAnalyses().map(a => ({
    id: `research-${a.id}`, title: a.title, subtitle: `${a.sport.toUpperCase()} / ${a.category} / Derived analysis`,
    href: `/analytics/research/${a.id}`, type: "module",
    keywords: [a.sport, a.category, a.description, a.source, ...a.fields.map(f => f.label)],
  }));
  const papers = loadPapers().map(p => ({
    id: `paper-${p.slug}`, title: p.title, subtitle: "Working paper", href: `/analytics/papers/${p.slug}`, type: "module",
    keywords: ["paper", "working paper", p.slug],
  }));
  const pages = SITE_PAGES.map(([href, title]) => ({
    id: `site-${href === "/" ? "home" : href.slice(1).replace(/\//g, "-")}`, title, subtitle: "Site page", href, type: "page", keywords: [title.toLowerCase()],
  }));
  // Drop frozen records that now resolve to a redirect stub (/analytics, /analytics/findings/retraction).
  const kept = (original.records as Array<{ href: string }>).filter(r => resolveRedirect(r.href.replace(/\/+$/, "") || "/") === null);
  return Response.json({ records: [...kept, ...derived, ...papers, ...pages, ...inspectorSearchRecords()] });
}
