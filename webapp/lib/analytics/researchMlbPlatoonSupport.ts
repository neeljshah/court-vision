import { field as f, snapshot } from "./labHelpers";
import type { ResearchAnalysis, ResearchReference, ResearchRow } from "./researchTypes";

type PlatoonEntry = {
  name?: unknown;
  rate_vs_l?: unknown;
  rate_vs_r?: unknown;
  platoon_delta?: unknown;
  pa_vs_l?: unknown;
  pa_vs_r?: unknown;
};
export type MlbPlatoonSource = {
  generated_at?: unknown;
  platoon_splits?: { top?: unknown; n_qualified?: unknown; floor?: unknown };
  observation_window?: { seasons?: unknown; corpus_id?: unknown; as_of?: unknown };
};

const SOURCE = "mlb_descriptive_leaderboards";
const FLOOR = "pa_vs_l>=50 and pa_vs_r>=50";
const REFERENCES: ResearchReference[] = [
  { title: "Published MLB descriptive leaderboard method", url: "https://github.com/neeljshah/court-vision/blob/master/scripts/platformkit/analytics_showcase/mlb_descriptive_leaderboards.py" },
  { title: "Published platoon split claims method", url: "https://github.com/neeljshah/court-vision/blob/master/scripts/platformkit/intel_validation/platoon_split_claims.py" },
  { title: "Published MLB descriptive snapshot", url: "https://github.com/neeljshah/court-vision/blob/master/webapp/public/data/showcase/mlb_descriptive_leaderboards.json" },
];
const rate = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;
const signedGap = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value) && value >= -1 && value <= 1;
const count = (value: unknown): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
const qualifiedCount = (value: unknown): number | null =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null;
const timestamp = (value: unknown): string =>
  typeof value === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value)
    && Number.isFinite(Date.parse(value)) ? value : "not published or invalid";

function selectionRows(top: unknown, floorVerified: boolean): ResearchRow[] {
  if (!Array.isArray(top)) return [];
  return top.flatMap((value, index) => {
    const entry: PlatoonEntry = typeof value === "object" && value !== null ? value : {};
    const name = typeof entry.name === "string" ? entry.name.trim() : "";
    if (!name) return [];
    const left = count(entry.pa_vs_l) ? entry.pa_vs_l : null;
    const right = count(entry.pa_vs_r) ? entry.pa_vs_r : null;
    const total = left !== null && right !== null ? left + right : null;
    const supportShare = floorVerified && left !== null && right !== null && left >= 50 && right >= 50
      && total !== null && Number.isSafeInteger(total) ? Math.min(left, right) / total : null;
    return [{
      id: `mlb-platoon-selection-${index}`,
      label: name,
      group: "Published upper selection",
      values: {
        smaller_side_support_share: supportShare,
        platoon_delta: signedGap(entry.platoon_delta) ? entry.platoon_delta : null,
        rate_vs_l: rate(entry.rate_vs_l) ? entry.rate_vs_l : null,
        rate_vs_r: rate(entry.rate_vs_r) ? entry.rate_vs_r : null,
        pa_vs_l: left,
        pa_vs_r: right,
      },
      note: `Published upper selection, not the full qualifying population. The source has no player ID or individual observation dates. Rates and gap are independently rounded in the source.${supportShare !== null ? "" : " Support share unavailable because both counts must be safe integers at the published floor and their sum must be a safe integer."}`,
      sourcePaths: ["name", "rate_vs_l", "rate_vs_r", "platoon_delta", "pa_vs_l", "pa_vs_r"]
        .map(key => `platoon_splits.top[${index}].${key}`),
    }];
  });
}

export function buildMlbPlatoonSupportResearch(source: MlbPlatoonSource): ResearchAnalysis {
  const selection = source?.platoon_splits;
  const floorVerified = selection?.floor === FLOOR;
  const rows = selectionRows(selection?.top, floorVerified);
  const published = Array.isArray(selection?.top) ? selection.top.length : 0;
  const qualified = qualifiedCount(selection?.n_qualified);
  const rawCorpusId = source?.observation_window?.corpus_id;
  const corpusId = typeof rawCorpusId === "string" && rawCorpusId.trim() ? rawCorpusId : "not published";
  const verifiedCorpus = source?.observation_window?.seasons === "2022_2023" && corpusId === "statcast_fuller_v1";
  const window = verifiedCorpus
    ? "fixed 2022-2023 sampled Statcast corpus" : "observation window not verified";
  const floor = floorVerified ? "at least 50 plate appearances against each pitcher hand" : "published floor not verified";
  const windowCaveat = verifiedCorpus
    ? "The 2022 and 2023 inputs are 18-day samples per season rather than full seasons."
    : "The source observation window or corpus ID is missing or unverified.";
  const floorCaveat = floorVerified
    ? "This showcase selection uses the published 50-PA-per-side floor; the separate claims validator uses a different 100-PA-per-side floor."
    : "This input's published floor is missing or unverified.";
  return {
    id: "mlb-platoon-support-balance",
    title: "MLB platoon split support balance",
    sport: "mlb",
    category: "Batter context",
    source: SOURCE,
    populationDefinition: {
      status: "unpublished",
      reason: "The snapshot publishes only its upper platoon-gap selection, not every floor-qualified batter. A full qualified distribution or league-wide ranking cannot be checked from these rows.",
    },
    question: "How balanced are the left- and right-handed pitcher plate-appearance counts behind each published split?",
    method: "Restate the published upper selections and compute the smaller of the two published plate-appearance counts divided by their sum.",
    description: "Shows the published on-base rates by pitcher hand beside the support balance behind each selected raw gap.",
    scope: `${rows.length} named rows from ${published} published upper selections${qualified === null ? "" : ` of ${qualified} floor-qualified batters`}; ${window}; ${floor}; source corpus ID ${corpusId}; source as-of timestamp ${timestamp(source?.observation_window?.as_of)}; public artifact generated ${timestamp(source?.generated_at)}.`,
    caveat: `${windowCaveat} The source as-of and artifact generation timestamps are not individual observation dates. The source counts plate-appearance-ending rows by pitcher throwing hand (p_throws); exact individual endpoints and player IDs are not published. ${floorCaveat} The selection omits other qualified batters. Rates and the published gap are rounded separately, so subtracting displayed rates can differ from the published gap. The producer reports an on-base-event rate, but the public snapshot does not list its event set or establish official OBP; the rates are unadjusted for park, opponent, or context. Support balance describes count mix, not precision, skill, persistence, or forecast performance.`,
    status: "Descriptive selected subset",
    fields: [
      f("smaller_side_support_share", "Smaller-side PA share", "percent", 2),
      f("platoon_delta", "Published vs-LHP minus vs-RHP gap", "pp", 2),
      f("rate_vs_l", "Published on-base-event rate vs LHP", "percent", 2),
      f("rate_vs_r", "Published on-base-event rate vs RHP", "percent", 2),
      f("pa_vs_l", "PA vs LHP", "number", 0),
      f("pa_vs_r", "PA vs RHP", "number", 0),
    ],
    rows,
    formula: "smaller_side_support_share = min(pa_vs_l, pa_vs_r) / (pa_vs_l + pa_vs_r); platoon_delta is copied from the separately rounded published value.",
    bindings: [
      { operand: "pa_vs_l", sourcePath: "platoon_splits.top[].pa_vs_l", valueKey: "pa_vs_l", label: "Published PA vs LHP" },
      { operand: "pa_vs_r", sourcePath: "platoon_splits.top[].pa_vs_r", valueKey: "pa_vs_r", label: "Published PA vs RHP" },
    ],
    interpretation: "A share near 50% means the two published support counts are similar; a lower share means one pitcher-hand side has fewer recorded plate appearances. Read it with both rates, the published gap, and both counts.",
    references: REFERENCES,
    novelty: "Derived analysis",
  };
}

export function getMlbPlatoonSupportResearch(): ResearchAnalysis[] {
  return [buildMlbPlatoonSupportResearch(snapshot<MlbPlatoonSource>(SOURCE))];
}
