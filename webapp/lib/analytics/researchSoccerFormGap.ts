import { field as f, snapshot } from "./labHelpers";
import type { ResearchAnalysis, ResearchReference, ResearchRow } from "./researchTypes";

export type SoccerFormGapEntry = {
  entity?: unknown;
  key_numbers?: Record<string, unknown>;
  floors?: unknown;
  as_of?: unknown;
};
export type SoccerFormGapAtlas = {
  generated_at?: unknown;
  n_entries?: unknown;
  entries?: unknown;
};

const WINDOW = /(?:^|[;( ])window=trailing10_asof_corpus_end(?=;|\)|$)/;
const HOME_FLOOR = /(?:^| \| )ppg_home_l10: n_prior_home>=10(?= \| | \()/;
const AWAY_FLOOR = /(?:^| \| )ppg_away_l10: n_prior_away>=10(?= \| | \()/;
const SOURCE_PATHS = [
  "entries[].key_numbers.ppg_home_l10",
  "entries[].key_numbers.ppg_away_l10",
];
const REFERENCES: ResearchReference[] = [{
  title: "Published soccer team-form producer",
  url: "https://github.com/neeljshah/court-vision/blob/master/scripts/platformkit/intel_validation/soccer_team_form_asof_claims.py",
}, {
  title: "Published soccer team atlas",
  url: "https://github.com/neeljshah/court-vision/blob/master/webapp/public/data/showcase/atlas_soccer_manifest.json",
}];

function slug(label: string): string {
  return label.toLowerCase().normalize("NFKD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

function validPpg(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 3;
}

function validTimestamp(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  const match = /^(\d{4}-\d{2}-\d{2})T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.exec(value);
  if (!match || !Number.isFinite(Date.parse(value))) return undefined;
  const midnight = Date.parse(`${match[1]}T00:00:00Z`);
  if (!Number.isFinite(midnight) || new Date(midnight).toISOString().slice(0, 10) !== match[1]) return undefined;
  return value;
}

function commonClaimTimestamp(entries: SoccerFormGapEntry[]): string | undefined {
  if (!entries.length) return undefined;
  const timestamps = entries.map(entry => validTimestamp(entry.as_of));
  if (timestamps.some(value => value === undefined)) return undefined;
  const unique = new Set(timestamps as string[]);
  return unique.size === 1 ? [...unique][0] : undefined;
}

function analysisRows(entries: SoccerFormGapEntry[]): ResearchRow[] {
  const labels = entries.map(entry => typeof entry.entity === "string" ? entry.entity.trim() : "");
  const slugs = labels.map(slug);
  const counts = new Map<string, number>();
  for (const value of slugs) if (value) counts.set(value, (counts.get(value) || 0) + 1);
  return entries.flatMap((entry, index) => {
    const label = labels[index];
    const id = slugs[index];
    const values = entry.key_numbers || {};
    const home = values.ppg_home_l10;
    const away = values.ppg_away_l10;
    const floors = typeof entry.floors === "string" ? entry.floors : "";
    if (!label || !id || counts.get(id) !== 1 || !validPpg(home) || !validPpg(away) ||
        !HOME_FLOOR.test(floors) || !AWAY_FLOOR.test(floors) || !WINDOW.test(floors)) return [];
    const gap = Math.round((home - away) * 10_000) / 10_000;
    if (gap < -3 || gap > 3) return [];
    return [{
      id: `soccer-form-gap-${id}`,
      label,
      group: "Trailing venue form",
      values: { home_minus_away_ppg: gap, ppg_home_l10: home, ppg_away_l10: away },
      note: `Team: ${label}. Source floors: n_prior_home>=10 and n_prior_away>=10. Each operand uses exactly 10 strictly prior matches at its venue; the match sets can cover different dates.`,
      sourcePaths: SOURCE_PATHS,
    }];
  }).sort((left, right) => right.values.home_minus_away_ppg! - left.values.home_minus_away_ppg! || left.label.localeCompare(right.label));
}

export function buildSoccerFormGapResearch(atlas: SoccerFormGapAtlas): ResearchAnalysis[] {
  const entries = Array.isArray(atlas?.entries)
    ? atlas.entries.filter((entry): entry is SoccerFormGapEntry => typeof entry === "object" && entry !== null)
    : [];
  const rows = analysisRows(entries);
  const published = typeof atlas?.n_entries === "number" && Number.isInteger(atlas.n_entries) && atlas.n_entries >= 0 ? atlas.n_entries : null;
  const computed = commonClaimTimestamp(entries);
  const generated = validTimestamp(atlas?.generated_at);
  return [{
    id: "soccer-home-away-trailing-form-gap",
    title: "Soccer form: home versus away",
    sport: "soccer",
    category: "Team matchup context",
    source: "atlas_soccer_manifest",
    description: "Compares each team's points per game across its separately computed trailing 10 prior home and away matches.",
    scope: `${rows.length} valid teams from ${published === null ? "the published soccer atlas" : `${published} published teams`}. Each operand independently clears its 10-match venue floor in the trailing10_asof_corpus_end snapshot.${computed ? ` Claim computation timestamp: ${computed}.` : " Claim computation timestamp is unavailable or inconsistent."}${generated ? ` Public artifact generation timestamp: ${generated}.` : ""}`,
    caveat: "The producer drops each team's latest match, then takes separate home and away tails of 10 from the remaining history. Those two match sets share the same team cutoff but can span different dates. The public atlas does not publish team-specific match dates, larger history counts, league membership, opponent strength, schedule composition, or promoted/relegated status. Its source covers six divisions from 2015-2026 without a published league partition here. The claim computation timestamp is not a match date, and artifact generation is separate. This is historical venue-split form context, not a causal effect or forecast.",
    status: "Descriptive",
    fields: [
      f("home_minus_away_ppg", "Home minus away PPG", "number", 2),
      f("ppg_home_l10", "Home PPG, prior 10", "number", 2),
      f("ppg_away_l10", "Away PPG, prior 10", "number", 2),
    ],
    rows,
    formula: "Home-minus-away PPG = published ppg_home_l10 - published ppg_away_l10, rounded to the source's four-decimal value precision.",
    bindings: [
      { operand: "ppg_home_l10", sourcePath: "entries[].key_numbers.ppg_home_l10", valueKey: "ppg_home_l10", label: "Home PPG, prior 10" },
      { operand: "ppg_away_l10", sourcePath: "entries[].key_numbers.ppg_away_l10", valueKey: "ppg_away_l10", label: "Away PPG, prior 10" },
    ],
    interpretation: "Positive values mean recorded home trailing-form PPG is higher; negative values mean recorded away trailing-form PPG is higher. Read both independently floored operands beside the difference.",
    references: REFERENCES,
    novelty: "Derived analysis",
  }];
}

export function getSoccerFormGapResearch(): ResearchAnalysis[] {
  return buildSoccerFormGapResearch(snapshot<SoccerFormGapAtlas>("atlas_soccer_manifest"));
}
