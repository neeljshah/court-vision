// Ranking and grouping for the command palette (CommandPaletteImpl). MiniSearch
// supplies fuzzy/prefix scores; this module puts exact title matches first, then
// title prefixes, then titles containing the phrase, then the rest by score, and
// orders the result groups so the best hit is the first item on screen.

export interface PaletteRecord {
  id: string;
  title: string;
  subtitle: string;
  href: string;
  type: "entity" | "module" | "finding" | "page";
  keywords: string[];
}
export type PaletteType = PaletteRecord["type"];

export const GROUP_ORDER: ReadonlyArray<{ type: PaletteType; heading: string }> = [
  { type: "page", heading: "Pages" },
  { type: "finding", heading: "Findings" },
  { type: "module", heading: "Modules" },
  { type: "entity", heading: "Entities" },
];

/** Offered when a query matches nothing: three pages a reader can start from. */
export const STARTING_POINTS: readonly PaletteRecord[] = [
  { id: "start-calibration", title: "Calibration", subtitle: "Pregame and in-game calibration against the market reference", href: "/analytics/calibration/", type: "page", keywords: ["calibration"] },
  { id: "start-retractions", title: "Retractions", subtitle: "Every withdrawn figure and why", href: "/evidence/retractions/", type: "page", keywords: ["retractions"] },
  { id: "start-paper-record", title: "Paper record", subtitle: "The forward paper series, counts only", href: "/paper-trading/", type: "page", keywords: ["paper record"] },
];

export function normalizeTitle(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

/** 0 exact title, 1 title starts with the query, 2 title contains the phrase, 3 anything else. */
export function titleTier(query: string, title: string): number {
  const q = normalizeTitle(query);
  const t = normalizeTitle(title);
  if (!q) return 3;
  if (t === q) return 0;
  if (t.startsWith(`${q} `) || t.startsWith(q)) return 1;
  if (` ${t} `.includes(` ${q} `)) return 2;
  return 3;
}

export interface ScoredHit { id: string | number; score: number }

const TYPE_PRIORITY: Record<PaletteType, number> = { page: 0, finding: 1, module: 2, entity: 3 };

/** Resolve search hits to records and sort them: title tier; within a title-matching tier
 *  page > finding > module > entity; then score, then title. */
export function rankHits(query: string, hits: ScoredHit[], lookup: (id: string) => PaletteRecord | undefined): PaletteRecord[] {
  return hits
    .flatMap((hit) => {
      const record = lookup(String(hit.id));
      return record ? [{ record, score: hit.score, tier: titleTier(query, record.title) }] : [];
    })
    .sort((a, b) => a.tier - b.tier
      || (a.tier < 3 ? TYPE_PRIORITY[a.record.type] - TYPE_PRIORITY[b.record.type] : 0)
      || b.score - a.score
      || a.record.title.localeCompare(b.record.title))
    .map((item) => item.record);
}

export interface PaletteGroup { type: PaletteType; heading: string; items: PaletteRecord[] }

/** Group ranked results by type. With a query, the group holding the best hit comes first. */
export function groupResults(results: PaletteRecord[], query: string): PaletteGroup[] {
  const groups = GROUP_ORDER
    .map((group) => ({ ...group, items: results.filter((record) => record.type === group.type) }))
    .filter((group) => group.items.length > 0);
  if (!query.trim()) return groups;
  const firstIndex = (group: PaletteGroup) => results.indexOf(group.items[0]);
  return groups.sort((a, b) => firstIndex(a) - firstIndex(b));
}
