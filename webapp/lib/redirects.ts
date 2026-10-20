// lib/redirects.ts -- the ONE map of retired routes (DESIGN_BRIEF 2026-10-20 section 3a).
// Static export: no server redirects exist, so each retired static route ships a
// stub page (components/shell/RedirectStub: meta refresh + canonical + visible link)
// and retired DYNAMIC families are caught by the root 404 page, whose inline script
// applies PREFIX_REDIRECTS to location.pathname. Paths are basePath-free, with a
// trailing slash (next.config trailingSlash: true). ASCII only.

export type Redirect = { to: string; label: string };

/** Exact retired routes -> new home. One stub page.tsx exists per key. */
export const REDIRECTS: Record<string, Redirect> = {
  "/atlas/": { to: "/analytics/players/", label: "Research: entity library" },
  "/live/": { to: "/games/", label: "Today: games" },
  "/p6/": { to: "/games/", label: "Today: games" },
  "/p6/system/": { to: "/desk/health/", label: "Desk: health" },
  "/p6/history/": { to: "/paper-trading/", label: "Desk: paper record" },
  "/bets/": { to: "/desk/", label: "Desk" },
  "/today/": { to: "/desk/", label: "Desk" },
  "/records/": { to: "/paper-trading/", label: "Desk: paper record" },
  "/risk/": { to: "/desk/", label: "Desk" },
  "/paper/": { to: "/paper-trading/", label: "Desk: paper record" },
  "/system/": { to: "/desk/health/", label: "Desk: health" },
  "/progress/": { to: "/desk/health/", label: "Desk: health" },
  "/models/": { to: "/desk/health/", label: "Desk: health" },
  "/evidence/retraction-story/": { to: "/evidence/retractions/", label: "Evidence: retraction record" },
  "/analytics/findings/retraction/": { to: "/evidence/retractions/", label: "Evidence: retraction record" },
  "/lab/": { to: "/analytics/lab/", label: "Research: measurement lab" },
  "/lab/counterfactual/": { to: "/analytics/state-reliability/", label: "Calibration: state reliability" },
  "/lab/microstructure/": { to: "/analytics/lab/", label: "Research: measurement lab" },
  "/analytics/": { to: "/", label: "Today (home)" },
  "/use-it/": { to: "/about/", label: "About" },
};

/** Retired dynamic families (no page is exported any more). ponytail: atlas pack and
 *  entity slugs differ from the analytics players slugs, so every atlas path lands on
 *  the library index; map slugs one by one only if deep links turn out to matter. */
export const PREFIX_REDIRECTS: Array<{ from: string; to: string }> = [
  { from: "/atlas/", to: "/analytics/players/" },
  { from: "/bets/", to: "/desk/" },
  { from: "/p6/", to: "/games/" },
  { from: "/paper/", to: "/paper-trading/" },
];

/** Resolve a basePath-free path to its new home, or null when it is not retired. */
export function resolveRedirect(path: string): string | null {
  const p = path.endsWith("/") ? path : `${path}/`;
  if (REDIRECTS[p]) return REDIRECTS[p].to;
  for (const r of PREFIX_REDIRECTS) {
    if (p.startsWith(r.from) && p !== r.from) return r.to;
  }
  return null;
}
