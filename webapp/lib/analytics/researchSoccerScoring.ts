import { field as f, snapshot } from "./labHelpers";
import type { ResearchAnalysis, ResearchReference, ResearchRow } from "./researchTypes";

export type SoccerScoringEntry = {
  entity?: unknown;
  key_numbers?: unknown;
  floors?: unknown;
  as_of?: unknown;
};
export type SoccerScoringAtlas = {
  generated_at?: unknown;
  n_entries?: unknown;
  entries?: unknown;
};

const WINDOW = /(?:^|[;( ])window=trailing10_asof_corpus_end(?=;|\)|$)/;
const METRICS = ["gd_l10", "gf_l10", "ga_l10"] as const;
const SOURCE = "atlas_soccer_manifest";
const REFERENCES: ResearchReference[] = [{
  title: "IFAB Laws of the Game, Law 10: Determining the Outcome of a Match",
  url: "https://www.theifab.com/laws/latest/determining-the-outcome-of-a-match/",
}, {
  title: "Published soccer team-form producer",
  url: "https://github.com/neeljshah/court-vision/blob/master/scripts/platformkit/intel_validation/soccer_team_form_asof_claims.py",
}];

function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function slug(label: string): string {
  return label.toLowerCase().normalize("NFKD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

function timestamp(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const match = /^(\d{4}-\d{2}-\d{2})T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.exec(value);
  if (!match || !Number.isFinite(Date.parse(value))) return null;
  const day = new Date(`${match[1]}T00:00:00Z`);
  return day.toISOString().slice(0, 10) === match[1] ? value : null;
}

function clears(floors: unknown, metric: typeof METRICS[number]): boolean {
  if (typeof floors !== "string" || !WINDOW.test(floors)) return false;
  const floor = new RegExp(`(?:^| \\| )${metric}: n_prior>=10(?= \\| | \\()`);
  return floor.test(floors);
}

function nonnegative(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;
}

function finite(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function round4(value: number): number {
  return Math.round((value + Number.EPSILON) * 10_000) / 10_000;
}

function rows(entries: SoccerScoringEntry[]): ResearchRow[] {
  const labels = entries.map(entry => typeof entry.entity === "string" ? entry.entity.trim() : "");
  const ids = labels.map(slug);
  const counts = new Map<string, number>();
  ids.forEach(id => { if (id) counts.set(id, (counts.get(id) || 0) + 1); });
  return entries.flatMap((entry, index) => {
    const label = labels[index];
    const suffix = ids[index];
    if (!label || !suffix || counts.get(suffix) !== 1) return [];
    const numbers = record(entry.key_numbers);
    const gf = clears(entry.floors, "gf_l10") ? nonnegative(numbers.gf_l10) : null;
    const ga = clears(entry.floors, "ga_l10") ? nonnegative(numbers.ga_l10) : null;
    const publishedGd = clears(entry.floors, "gd_l10") ? finite(numbers.gd_l10) : null;
    const coherent = publishedGd !== null && gf !== null && ga !== null && round4(publishedGd) === round4(gf - ga);
    const gd = coherent ? publishedGd : null;
    const claimTime = timestamp(entry.as_of);
    const unavailable = METRICS.filter(metric => ({ gd_l10: gd, gf_l10: gf, ga_l10: ga })[metric] === null);
    const windows = Object.fromEntries(METRICS.map(metric => [metric, clears(entry.floors, metric)
      ? "exactly 10 strictly prior all-venue matches; latest per-team match dropped"
      : "unavailable: exact n_prior>=10 floor and trailing10_asof_corpus_end window not verified"]));
    return [{
      id: `soccer-scoring-${suffix}`,
      label,
      group: "Trailing scoring form",
      values: { gd_l10: gd, gf_l10: gf, ga_l10: ga },
      note: `Team: ${label}. Each available field clears n_prior>=10 and uses exactly 10 strictly prior all-venue matches after the team's latest match was dropped.${unavailable.length ? ` Unavailable: ${unavailable.join(", ")}.${publishedGd !== null && !coherent ? " Published goal difference could not be verified as goals scored minus goals conceded at four decimals." : ""}` : ""} Per-team match dates are not published; source claim timestamp: ${claimTime ?? "unavailable"}.`,
      sourcePaths: METRICS.map(metric => `entries[${index}].key_numbers.${metric}`),
      bindingValues: { source_claim_timestamp: claimTime },
      windows,
    }];
  });
}

export function buildSoccerScoringResearch(atlas: SoccerScoringAtlas): ResearchAnalysis {
  const entries: SoccerScoringEntry[] = Array.isArray(atlas?.entries)
    ? atlas.entries.map(entry => entry !== null && typeof entry === "object" && !Array.isArray(entry) ? entry as SoccerScoringEntry : {})
    : [];
  const resultRows = rows(entries);
  const claimDates = entries.map(entry => timestamp(entry.as_of));
  const uniqueDates = new Set(claimDates.filter((value): value is string => value !== null));
  const claimAsOf = claimDates.length > 0 && claimDates.every(Boolean) && uniqueDates.size === 1 ? [...uniqueDates][0] : "not published or inconsistent";
  const generated = timestamp(atlas?.generated_at);
  const published = typeof atlas?.n_entries === "number" && Number.isSafeInteger(atlas.n_entries) && atlas.n_entries >= 0 ? atlas.n_entries : null;
  return {
    id: "soccer-trailing-attack-defense",
    title: "Soccer form: attack and defense",
    sport: "soccer",
    category: "Team matchup context",
    source: SOURCE,
    status: "Descriptive",
    novelty: "Derived analysis",
    fields: [
      f("gd_l10", "Goal difference per game", "number", 2),
      f("gf_l10", "Goals scored per game", "number", 2),
      f("ga_l10", "Goals conceded per game", "number", 2),
    ],
    rows: resultRows,
    description: "Compares published team attack and defense scoring rates over each team's trailing 10 strictly prior all-venue matches.",
    question: "How do published recent goals scored, goals conceded, and goal difference compare across teams?",
    scope: `${resultRows.length} valid unique team rows from ${published === null ? "the published soccer atlas" : `${published} published rows`}. Source claim timestamp: ${claimAsOf}. Public artifact generation timestamp: ${generated ?? "not published"}.`,
    caveat: "This descriptive source pools six divisions and seasons 2015-2026 without a league partition or opponent-strength adjustment. Team schedules overlap, so rows are not independent. Each team has its own latest-match cutoff; the claim timestamp and artifact generation timestamp are not per-team match dates and do not imply synchronized windows. The public artifact omits those match dates. These rates do not measure expected goals, forecast outcomes, or establish causes.",
    method: "For each field, require its exact published n_prior>=10 floor and window=trailing10_asof_corpus_end. Accept finite goals scored and conceded only when nonnegative. Keep missing or invalid fields null. Publish goal difference only when its source value equals source goals scored minus goals conceded at four-decimal precision.",
    formula: "gd_l10 = gf_l10 - ga_l10 at the producer's four-decimal source precision; all three fields are published per-game means over exactly 10 strictly prior matches.",
    interpretation: "Higher goals scored means more recorded recent scoring; lower goals conceded means fewer recorded recent goals allowed. Goal difference combines those descriptive rates. Compare them with league, opponent and schedule limits in view.",
    sources: [{
      id: SOURCE,
      asOf: claimAsOf,
      fields: [...METRICS],
      rowWindows: Object.fromEntries(METRICS.map(metric => [metric, [
        ...new Set(resultRows.map(row => row.windows?.[metric]).filter((value): value is string => typeof value === "string")),
        "per-team match dates not published",
      ]])),
    }],
    bindings: [
      { operand: "gd_l10", sourcePath: "entries[i].key_numbers.gd_l10", valueKey: "gd_l10", label: "Published goal difference per game" },
      { operand: "gf_l10", sourcePath: "entries[i].key_numbers.gf_l10", valueKey: "gf_l10", label: "Published goals scored per game" },
      { operand: "ga_l10", sourcePath: "entries[i].key_numbers.ga_l10", valueKey: "ga_l10", label: "Published goals conceded per game" },
      { operand: "source_claim_timestamp", sourcePath: "entries[i].as_of", valueKey: "source_claim_timestamp", label: "Published source claim timestamp" },
    ],
    references: REFERENCES,
  };
}

export function getSoccerScoringResearch(): ResearchAnalysis {
  return buildSoccerScoringResearch(snapshot<SoccerScoringAtlas>(SOURCE));
}
