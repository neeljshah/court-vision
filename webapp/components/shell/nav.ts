// components/shell/nav.ts -- the ONE six-item site nav (DESIGN_BRIEF 2026-10-20 section 3)
// plus the pathname -> section and pathname -> breadcrumb rules. Paths are basePath-free.

export type Section = { label: string; href: string; match: RegExp };

export const SITE_NAV: readonly Section[] = [
  { label: "Today", href: "/", match: /^\/(games)(\/|$)/ },
  { label: "Desk", href: "/desk/", match: /^\/(desk|paper-trading|paper)(\/|$)/ },
  {
    label: "Calibration",
    href: "/analytics/calibration/",
    match: /^\/analytics\/(calibration|state-reliability|state-contrasts|forecaster|compare|score-decomposition|residual-anatomy|observation-dependence|cross-sport-comparability)(\/|$)/,
  },
  {
    label: "Research",
    href: "/analytics/papers/",
    match: /^\/(graveyard|analytics\/(papers|ask|findings|novel|lab|players|browse|research|m|the-loop|blowout-timing|pitch-sequencing|count-context))(\/|$)/,
  },
  { label: "Evidence", href: "/evidence/", match: /^\/(evidence|receipts|analytics\/evidence)(\/|$)/ },
  { label: "About", href: "/about/", match: /^\/(about|how-it-works|methodology|analytics\/(about|explainers))(\/|$)/ },
];

export const GITHUB = "https://github.com/neeljshah/court-vision";
export const githubDoc = (path: string) => `${GITHUB}/blob/master/${path}`;
export const CONTACT_EMAIL = "neeljshah22@gmail.com";
export const PORTFOLIO = "https://neelshahportfolio.netlify.app/";

/** Strip the export basePath and any trailing slash; "" becomes "/". */
export function normalizePath(raw: string | null | undefined): string {
  const p = (raw || "/").replace(/^\/court-vision(?=\/|$)/, "").replace(/\/+$/, "");
  return p || "/";
}

/** Route group: /analytics pages load analytics.css, everything else globals.css. */
export const group = (path: string): "analytics" | "site" =>
  /^\/analytics(\/|$)/.test(normalizePath(path)) ? "analytics" : "site";

export function sectionFor(raw: string | null | undefined): Section | null {
  const p = normalizePath(raw);
  if (p === "/") return SITE_NAV[0];
  return SITE_NAV.find((s) => normalizePath(s.href) === p || s.match.test(p)) ?? null;
}

// Segment labels where humanizing the slug reads badly.
const LABELS: Record<string, string> = {
  "paper-trading": "Paper record",
  "how-it-works": "How it works",
  "model-cards": "Model cards",
  ingame: "In-game",
  retractions: "Retraction record",
  novel: "Experimental metrics",
  lab: "Measurement lab",
  players: "Entity library",
  browse: "Library",
  m: "Modules",
  "the-loop": "Research loop",
  nba: "NBA",
  mlb: "MLB",
  atp: "ATP",
};

// Intermediate paths that have an index page; other intermediate crumbs render as text.
const INDEXES = new Set([
  "/desk", "/games", "/evidence", "/receipts", "/analytics/papers", "/analytics/findings",
  "/analytics/explainers", "/analytics/players",
]);

export function humanize(seg: string): string {
  if (LABELS[seg]) return LABELS[seg];
  let s = seg;
  try { s = decodeURIComponent(seg); } catch { /* keep raw */ }
  s = s.replace(/[-_]+/g, " ").trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export type Crumb = { label: string; href: string | null };

/** Home > Section > ... > Page. Empty on "/" and on a section root. */
export function crumbsFor(raw: string | null | undefined): Crumb[] {
  const p = normalizePath(raw);
  const section = sectionFor(p);
  if (p === "/" || (section && normalizePath(section.href) === p)) return [];
  const out: Crumb[] = [{ label: "Home", href: "/" }];
  const sectionPath = section ? normalizePath(section.href) : null;
  if (section && section.href !== "/") out.push({ label: section.label, href: section.href });
  const segs = p.split("/").filter(Boolean);
  segs.forEach((seg, i) => {
    const path = `/${segs.slice(0, i + 1).join("/")}`;
    if (path === "/analytics" || path === sectionPath) return;
    const last = i === segs.length - 1;
    out.push({ label: humanize(seg), href: !last && INDEXES.has(path) ? `${path}/` : null });
  });
  return out;
}
