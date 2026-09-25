import { field as f, snapshot } from "./labHelpers";
import type { ResearchAnalysis, ResearchReference, ResearchRow } from "./researchTypes";

type Entry = {
  player_name?: unknown;
  clay_minus_hard?: unknown;
  clay_wr?: unknown;
  hard_wr?: unknown;
  clay_n?: unknown;
  hard_n?: unknown;
};
type Gap = { floor?: unknown; n_qualifying?: unknown; most_clay_favoring?: unknown; most_hard_favoring?: unknown };
type Combo = { status?: unknown; source?: unknown; clay_hard_gap?: Gap };
export type TennisMatchSupportSource = { floors?: { clay_hard_gap?: unknown }; combos?: Record<string, Combo> };

const SOURCE = "tennis_surface_transfer";
const FLOOR = "clay_n>=25 AND hard_n>=25";
const WINDOWS = [
  { key: "atp_career", label: "ATP career", suffix: "career", window: "dated matches in the pooled 2015-2025 corpus" },
  { key: "atp_recent_form", label: "ATP recent form", suffix: "recent form", window: "matches on or after 2023-01-01 in that corpus" },
] as const;
const SELECTIONS = ["most_clay_favoring", "most_hard_favoring"] as const;
const REFERENCES: ResearchReference[] = [
  { title: "Published tennis surface-context method", url: "https://github.com/neeljshah/court-vision/blob/master/scripts/platformkit/intel_validation/tennis_surface_context_claims.py" },
  { title: "Published tennis surface-transfer method", url: "https://github.com/neeljshah/court-vision/blob/master/scripts/platformkit/analytics_showcase/tennis_surface_transfer.py" },
  { title: "Published tennis surface-transfer snapshot", url: "https://github.com/neeljshah/court-vision/blob/master/webapp/public/data/showcase/tennis_surface_transfer.json" },
];
const rate = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;
const gap = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value) && value >= -1 && value <= 1;
const count = (value: unknown): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
const metadataCount = (value: unknown): number | null => count(value) ? value : null;

function selectionRows(comboKey: string, label: string, suffix: string, window: string, source: Gap, floorVerified: boolean): ResearchRow[] {
  return SELECTIONS.flatMap(selection => {
    const values = source[selection];
    if (!Array.isArray(values)) return [];
    return values.flatMap((value, index) => {
      const entry: Entry = typeof value === "object" && value !== null ? value : {};
      const name = typeof entry.player_name === "string" ? entry.player_name.trim() : "";
      if (!name) return [];
      const clay = count(entry.clay_n) ? entry.clay_n : null;
      const hard = count(entry.hard_n) ? entry.hard_n : null;
      const total = clay !== null && hard !== null ? clay + hard : null;
      const share = floorVerified && clay !== null && hard !== null && clay >= 25 && hard >= 25
        && total !== null && Number.isSafeInteger(total) ? Math.min(clay, hard) / total : null;
      const path = `combos.${comboKey}.clay_hard_gap.${selection}[${index}]`;
      return [{
        id: `tennis-clay-hard-${comboKey}-${selection}-${index}`,
        label: `${name} (${suffix})`,
        group: label,
        values: {
          smaller_surface_match_share: share,
          clay_minus_hard: gap(entry.clay_minus_hard) ? entry.clay_minus_hard : null,
          clay_wr: rate(entry.clay_wr) ? entry.clay_wr : null,
          hard_wr: rate(entry.hard_wr) ? entry.hard_wr : null,
          clay_n: clay,
          hard_n: hard,
        },
        note: `Published ${selection.replace(/_/g, " ")} extreme for ${name}. The ${suffix} window is ${window}. Match counts are from the same window; player-specific endpoint dates are not published.${share === null ? " Balance unavailable without both floor-qualified safe counts and a safe sum." : ""}`,
        windows: { clay_n: window, hard_n: window },
        sourcePaths: ["player_name", "clay_minus_hard", "clay_wr", "hard_wr", "clay_n", "hard_n"].map(key => `${path}.${key}`),
      }];
    });
  });
}

export function buildTennisMatchSupportResearch(source: TennisMatchSupportSource): ResearchAnalysis[] {
  const summaries: string[] = [];
  const rows = WINDOWS.flatMap(({ key, label, suffix, window }) => {
    const combo = source?.combos?.[key];
    const verifiedWindow = combo?.status === "ok" && combo.source === `data/cache/intel_claims/tennis_surface_context_snapshot_${key}.parquet`;
    const gapSource = combo?.clay_hard_gap;
    const arrays = SELECTIONS.map(selection => gapSource?.[selection]);
    const published = arrays.reduce<number>((sum, values) => sum + (Array.isArray(values) ? values.length : 0), 0);
    const qualified = metadataCount(gapSource?.n_qualifying);
    summaries.push(`${label}: ${published} published extremes${qualified === null ? " (qualifier count unavailable)" : ` from ${qualified} qualifiers`}${verifiedWindow ? `; ${window}` : "; source window unverified"}`);
    if (!verifiedWindow || !gapSource) return [];
    const floorVerified = source?.floors?.clay_hard_gap === FLOOR && gapSource.floor === FLOOR;
    return selectionRows(key, label, suffix, window, gapSource, floorVerified);
  });
  return [{
    id: "tennis-clay-hard-match-support",
    title: "Tennis clay-hard match support balance",
    sport: "tennis",
    category: "Surface context",
    source: SOURCE,
    populationDefinition: {
      status: "unpublished",
      reason: "The snapshot publishes only selected extremes in each ATP window, not the full qualifying player rows. A complete player ranking or pooled percentile cannot be verified.",
    },
    question: "How balanced are the clay and hard match counts behind each published player gap?",
    method: "Keep the source's ATP career and recent-form extreme rows separate and divide the smaller published surface match count by their sum.",
    description: "Places clay-versus-hard match-count balance beside the published surface win-rate gap and both support counts.",
    scope: `${summaries.join(". ")}. ${rows.length} named rows retained. Balance requires the verified 25-match floor on each surface; the source publishes no player-specific latest match dates or analysis as-of timestamp.`,
    caveat: "Recent form overlaps the pooled career corpus; the rows are not independent periods. The source publishes only selected extremes, and ATP/WTA populations must not be pooled. Opponent strength, draws, age, schedule, and retirement endings are uncontrolled. Published rates and gap are source-rounded, so the gap is copied rather than recomputed. Count balance describes support mix, not precision, surface skill, persistence, or forecast performance.",
    status: "Descriptive selected subset",
    fields: [
      f("smaller_surface_match_share", "Smaller-surface match share", "percent", 2),
      f("clay_minus_hard", "Published clay minus hard win rate", "pp", 2),
      f("clay_wr", "Clay win rate", "percent", 2),
      f("hard_wr", "Hard win rate", "percent", 2),
      f("clay_n", "Clay matches", "number", 0),
      f("hard_n", "Hard matches", "number", 0),
    ],
    rows,
    formula: "smaller_surface_match_share = min(clay_n, hard_n) / (clay_n + hard_n); clay_minus_hard is copied from the published source-rounded gap.",
    bindings: [
      { operand: "clay_n", sourcePath: "combos.*.clay_hard_gap.*[].clay_n", valueKey: "clay_n", label: "Published clay matches" },
      { operand: "hard_n", sourcePath: "combos.*.clay_hard_gap.*[].hard_n", valueKey: "hard_n", label: "Published hard matches" },
    ],
    interpretation: "A share near 50% means similar match counts on clay and hard; a smaller share means one surface has fewer recorded matches. Compare within the named window and read both rates and counts alongside the published gap.",
    references: REFERENCES,
    novelty: "Derived analysis",
  }];
}

export function getTennisMatchSupportResearch(): ResearchAnalysis[] {
  return buildTennisMatchSupportResearch(snapshot<TennisMatchSupportSource>(SOURCE));
}
