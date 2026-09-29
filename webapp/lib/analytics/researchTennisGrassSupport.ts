import { field as f, snapshot } from "./labHelpers";
import type { ResearchAnalysis, ResearchReference, ResearchRow } from "./researchTypes";

type Entry = {
  player_name?: unknown;
  grass_adapt?: unknown;
  grass_wr?: unknown;
  ov_wr?: unknown;
  grass_n?: unknown;
};
type Grass = { floor?: unknown; n_qualifying?: unknown; most_adaptive?: unknown; least_adaptive?: unknown };
type Combo = { status?: unknown; source?: unknown; n_players_in_snapshot?: unknown; grass_adaptability?: Grass };
export type TennisGrassSupportSource = { floors?: { grass_adaptability?: unknown }; combos?: Record<string, Combo> };

const SOURCE = "tennis_surface_transfer";
const FLOOR = "grass_n>=15";
const WINDOWS = [
  { key: "atp_career", label: "ATP career", suffix: "career", window: "dated matches in the pooled 2015-2025 corpus" },
  { key: "atp_recent_form", label: "ATP recent form", suffix: "recent form", window: "matches on or after 2023-01-01 in that corpus" },
] as const;
const SELECTIONS = ["most_adaptive", "least_adaptive"] as const;
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

function selectionRows(comboKey: string, label: string, suffix: string, window: string, source: Grass, floorVerified: boolean): ResearchRow[] {
  return SELECTIONS.flatMap(selection => {
    const values = source[selection];
    if (!Array.isArray(values)) return [];
    return values.flatMap((value, index) => {
      const entry: Entry = typeof value === "object" && value !== null ? value : {};
      const name = typeof entry.player_name === "string" ? entry.player_name.trim() : "";
      if (!name) return [];
      const grassN = count(entry.grass_n) ? entry.grass_n : null;
      const step = floorVerified && grassN !== null && grassN >= 15 ? 1 / grassN : null;
      const path = `combos.${comboKey}.grass_adaptability.${selection}[${index}]`;
      return [{
        id: `tennis-grass-${comboKey}-${selection}-${index}`,
        label: `${name} (${suffix})`,
        group: label,
        values: {
          one_result_step: step,
          grass_adapt: gap(entry.grass_adapt) ? entry.grass_adapt : null,
          grass_wr: rate(entry.grass_wr) ? entry.grass_wr : null,
          ov_wr: rate(entry.ov_wr) ? entry.ov_wr : null,
          grass_n: grassN,
        },
        note: `Published ${selection.replace(/_/g, " ")} extreme for ${name}. The ${suffix} window is ${window}. Grass matches are from that window; player-specific endpoint dates are not published.${step === null ? " One-result step unavailable without the verified 15-match floor and a safe count." : " One-result step is hypothetical at fixed grass match count; overall win rate includes grass."}`,
        windows: { grass_n: window },
        sourcePaths: ["player_name", "grass_adapt", "grass_wr", "ov_wr", "grass_n"].map(key => `${path}.${key}`),
      }];
    });
  });
}

export function buildTennisGrassSupportResearch(source: TennisGrassSupportSource): ResearchAnalysis[] {
  const summaries: string[] = [];
  const rows = WINDOWS.flatMap(({ key, label, suffix, window }) => {
    const combo = source?.combos?.[key];
    const verifiedWindow = combo?.status === "ok" && combo.source === `data/cache/intel_claims/tennis_surface_context_snapshot_${key}.parquet`;
    const grassSource = combo?.grass_adaptability;
    const arrays = SELECTIONS.map(selection => grassSource?.[selection]);
    const selectionCountsKnown = arrays.every(Array.isArray);
    const published = arrays.reduce<number>((sum, values) => sum + (Array.isArray(values) ? values.length : 0), 0);
    const longestSelection = Math.max(...arrays.map(values => Array.isArray(values) ? values.length : 0));
    const qualified = metadataCount(grassSource?.n_qualifying);
    const snapshotPlayers = metadataCount(combo?.n_players_in_snapshot);
    const inconsistent = qualified !== null && (longestSelection > qualified || (snapshotPlayers !== null && snapshotPlayers < qualified));
    const denominator = verifiedWindow && !inconsistent && qualified !== null && snapshotPlayers !== null
      ? ` among ${snapshotPlayers.toLocaleString("en-US")} snapshot player rows` : "";
    summaries.push(`${label}: ${selectionCountsKnown ? `${published} published extremes` : "published selection count unavailable"}${qualified === null ? " (qualifier count unavailable)" : ` from ${qualified} qualifying rows${denominator}`}${inconsistent ? " (source row counts inconsistent; snapshot denominator withheld)" : ""}${verifiedWindow ? `; ${window}` : "; source window unverified"}`);
    if (!verifiedWindow || !grassSource) return [];
    const floorVerified = source?.floors?.grass_adaptability === FLOOR && grassSource.floor === FLOOR;
    return selectionRows(key, label, suffix, window, grassSource, floorVerified);
  });
  return [{
    id: "tennis-grass-overall-match-support",
    title: "Tennis grass win rates and match support",
    sport: "tennis",
    category: "Surface context",
    source: SOURCE,
    populationDefinition: {
      status: "unpublished",
      reason: "The snapshot publishes only selected ATP tails, not all qualifying player rows. A complete ranking, pooled percentile, or eligible population cannot be verified.",
    },
    question: "How many grass matches support each published grass-versus-overall gap?",
    method: "Keep the source's ATP career and recent-form selected rows separate, copy the published gap, and divide one by the grass match count when the published floor is verified.",
    description: "Read published grass win rates and grass-versus-overall gaps alongside their grass match counts. The one-match step describes only the grass win rate at a fixed match count.",
    scope: `${summaries.join(". ")}. ${rows.length} named rows retained. The step requires the verified 15-grass-match floor. Counts describe source-reported rows, not verified distinct people; no player-specific latest match dates or analysis as-of timestamp are published.`,
    caveat: "Recent form overlaps the pooled career corpus; these are not independent windows. Overall win rate includes grass, and the source provides no overall match count, so no independent overall support or grass share is inferred. Only hard, clay, and grass matches feed the upstream rates; unknown and carpet are excluded. The producer counts decided retirement outcomes using the stored winner. Player identity is name-only. ATP and WTA must not be pooled. Opponent strength, draws, age, and schedule are uncontrolled. The published gap is copied because source-rounded rates need not subtract exactly. The step is a hypothetical change to grass win rate at fixed grass count; it is not the grass-minus-overall gap's one-result change because overall win rate would also change. It is not a confidence interval, error bar, causal effect, prediction, or surface skill estimate.",
    status: "Descriptive selected subset",
    fields: [
      f("one_result_step", "One grass-match rate step", "pp", 2),
      f("grass_adapt", "Published grass minus overall win rate", "pp", 2),
      f("grass_wr", "Grass win rate", "percent", 2),
      f("ov_wr", "Overall win rate", "percent", 2),
      f("grass_n", "Grass matches", "number", 0),
    ],
    rows,
    formula: "one_result_step = 1 / grass_n in grass win-rate units (displayed as 100 / grass_n percentage points) for floor-qualified rows; grass_adapt is copied from the published source-rounded gap. The gap's one-result change cannot be calculated without the unpublished overall match count.",
    bindings: [{ operand: "grass_n", sourcePath: "combos.*.grass_adaptability.*[].grass_n", valueKey: "grass_n", label: "Published grass matches" }],
    interpretation: "A larger step means each recorded grass result is a larger fraction of the published grass sample. Compare within the named window and read the count with both source rates and the copied gap.",
    references: REFERENCES,
    novelty: "Derived analysis",
  }];
}

export function getTennisGrassSupportResearch(): ResearchAnalysis[] {
  return buildTennisGrassSupportResearch(snapshot<TennisGrassSupportSource>(SOURCE));
}
