import type { ResearchAnalysis, ResearchField, ResearchRow } from "./researchTypes";

export type NbaVariabilitySource = {
  as_of?: unknown;
  methodology?: unknown;
  input_coverage?: unknown;
  most_consistent_top15?: unknown;
  least_consistent_top15?: unknown;
};

type Entry = Record<string, unknown>;
const SOURCE = "nba_consistency_profiles";
const STATS = ["pts", "reb", "ast"] as const;
const record = (value: unknown): Entry => value !== null && typeof value === "object" && !Array.isArray(value) ? value as Entry : {};
const nonnegative = (value: unknown): number | null => typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;
const count = (value: unknown): number | null => typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null;
const text = (value: unknown): string => typeof value === "string" ? value.trim() : "";
const field = (key: string, label: string, unit: ResearchField["unit"] = "number", digits = 4): ResearchField => ({ key, label, unit, digits, sourceId: SOURCE });
const delta = (value: number | null, prior: number | null): number | null => {
  if (value === null || prior === null) return null;
  const result = value - prior;
  return Number.isFinite(result) ? result : null;
};
function date(value: unknown): string | undefined {
  const candidate = text(value);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(candidate)) return undefined;
  const parsed = new Date(`${candidate}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === candidate ? candidate : undefined;
}
function seasons(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && item.trim().length > 0) : [];
}

/** Build a descriptive research view from the published NBA variability snapshot. */
export function buildNbaVariabilityResearch(source: NbaVariabilitySource): ResearchAnalysis {
  const methodology = record(source.methodology);
  const coverage = record(source.input_coverage);
  const priors = record(methodology.league_mean_cv_raw);
  const low = Array.isArray(source.most_consistent_top15) ? source.most_consistent_top15 : [];
  const high = Array.isArray(source.least_consistent_top15) ? source.least_consistent_top15 : [];
  const priorValues = Object.fromEntries(STATS.map(stat => [stat, nonnegative(priors[stat])]));
  const rows: ResearchRow[] = [];

  for (const [arrayKey, sourceRows, group, offset] of [
    ["most_consistent_top15", low, "Published low-CV subset", 0],
    ["least_consistent_top15", high, "Published high-CV subset", low.length],
  ] as const) {
    sourceRows.forEach((raw, index) => {
      const entry = record(raw);
      const name = text(entry.player_name);
      if (!name) return;
      const prefix = `${SOURCE}.${arrayKey}[${index}]`;
      const cvs = STATS.map(stat => nonnegative(entry[`${stat}_cv_shrunk`]));
      const complete = cvs.every(value => value !== null);
      const cvMax = complete ? Math.max(...cvs as number[]) : null;
      const cvMin = complete ? Math.min(...cvs as number[]) : null;
      const range = delta(cvMax, cvMin);
      const weight = nonnegative(entry.shrink_weight);
      rows.push({
        id: `consistency-${offset + index}`,
        label: name,
        group,
        values: {
          cv_range: range, cv_max: cvMax, cv_min: cvMin,
          pts_cv: cvs[0], reb_cv: cvs[1], ast_cv: cvs[2], games: count(entry.games),
          pts_cv_vs_prior: delta(cvs[0], priorValues.pts),
          reb_cv_vs_prior: delta(cvs[1], priorValues.reb),
          ast_cv_vs_prior: delta(cvs[2], priorValues.ast),
          shrink_weight: weight !== null && weight <= 1 ? weight : null,
        },
        bindingValues: {
          pts_prior: priorValues.pts, reb_prior: priorValues.reb, ast_prior: priorValues.ast,
        },
        sourcePaths: [
          `${prefix}.player_name`, `${prefix}.player_id`,
          ...STATS.map(stat => `${prefix}.${stat}_cv_shrunk`),
          `${prefix}.games`, `${prefix}.shrink_weight`,
          ...STATS.map(stat => `${SOURCE}.methodology.league_mean_cv_raw.${stat}`),
        ],
      });
    });
  }

  const publishedSeasons = seasons(coverage.seasons).length ? seasons(coverage.seasons) : seasons(methodology.seasons_pooled);
  const floorGames = count(methodology.min_qualifying_games_floor);
  const floorMinutes = nonnegative(methodology.min_game_minutes_floor);
  const eligible = count(coverage.players_meeting_floor);
  const asOf = date(source.as_of);
  const shrinkK = nonnegative(methodology.shrink_k_games);
  const scopeParts = [`${rows.length} published players from the two selected CV extremes`];
  if (eligible !== null) scopeParts.push(`${eligible} players meeting the published floor`);
  if (publishedSeasons.length) scopeParts.push(`seasons ${publishedSeasons.join(", ")}`);
  if (floorGames !== null) scopeParts.push(`at least ${floorGames} qualifying games`);
  if (floorMinutes !== null) scopeParts.push(`at least ${floorMinutes} minutes per qualifying game`);
  if (asOf) scopeParts.push(`source as of ${asOf}`);

  return {
    id: "nba-variability-imbalance", title: "NBA variability and its league baseline", sport: "nba",
    category: "Player profiles", source: SOURCE, novelty: "Derived analysis", status: "Descriptive subset",
    description: "Published shrunk points, rebounds, and assists CVs compared with their same-snapshot league mean raw CV priors.",
    scope: `${scopeParts.join("; ")}.`,
    populationDefinition: { status: "unpublished", reason: "Only the published extremes are available as player rows, not the complete eligible population." },
    caveat: "Only selected extremes are shown. Raw per-player standard deviations and per-stat valid counts are unavailable; the games column counts appearances meeting the minutes floor. The league reference includes each selected player and is not an independent comparison sample. CV rises mechanically when a stat mean is low. Cross-stat gaps are not standardized. These historical values do not measure skill, forecast uncertainty, or causal effects.",
    fields: [
      field("cv_range", "Shrunk CV range"), field("cv_max", "Highest shrunk stat CV"), field("cv_min", "Lowest shrunk stat CV"),
      field("pts_cv", "Points shrunk CV"), field("reb_cv", "Rebounds shrunk CV"), field("ast_cv", "Assists shrunk CV"),
      field("games", "Qualifying games", "number", 0),
      field("pts_cv_vs_prior", "Points: shrunk CV minus prior"),
      field("reb_cv_vs_prior", "Rebounds: shrunk CV minus prior"),
      field("ast_cv_vs_prior", "Assists: shrunk CV minus prior"),
      field("shrink_weight", "Source shrink weight", "percent", 1),
    ],
    rows,
    bindings: [
      ...STATS.map(stat => ({ operand: `${stat}_shrunk_cv`, sourcePath: `${SOURCE}.*[].${stat}_cv_shrunk`, valueKey: `${stat}_cv`, label: `${stat.toUpperCase()} shrunk CV` })),
      ...STATS.map(stat => ({ operand: `${stat}_prior`, sourcePath: `${SOURCE}.methodology.league_mean_cv_raw.${stat}`, valueKey: `${stat}_prior`, label: `${stat.toUpperCase()} raw league mean CV prior` })),
      { operand: "qualifying_games", sourcePath: `${SOURCE}.*[].games`, valueKey: "games", label: "Qualifying games" },
      { operand: "shrink_weight", sourcePath: `${SOURCE}.*[].shrink_weight`, valueKey: "shrink_weight", label: "Source shrink weight" },
    ],
    formula: `For each stat, raw CV = sample standard deviation (ddof=1) / mean of qualifying per-36 game rates. Source shrinkage: shrunk CV = w * raw player CV + (1 - w) * same-snapshot league mean raw CV, with w = games / (games + K)${shrinkK === null ? "; K is not published" : ` and source K = ${shrinkK} games`}. The published weight is the raw-player-CV share of the blend, not a confidence score. The prior is the unweighted mean of qualifying players' raw CVs, not a pooled game CV. Signed gap = published shrunk CV - published raw league mean CV prior. CV range = max(three published shrunk CVs) - min(three published shrunk CVs).`,
    interpretation: "A positive signed gap means the published shrunk stat CV exceeds its same-snapshot prior; a negative gap means it is below. Gaps are dimensionless CV units, not percentage points. Shrinkage attenuates each gap toward that prior. Published four-decimal CVs and priors make calculated gaps approximate; the source weight is rounded to three decimals. The within-player range does not identify a universally most unstable role.",
    references: [
      { title: "NIST coefficient of variation", url: "https://www.itl.nist.gov/div898/software/dataplot/refman2/auxillar/coefvari.htm" },
      { title: "Published NBA consistency producer", url: "https://github.com/neeljshah/court-vision/blob/master/scripts/platformkit/analytics_showcase/nba_consistency_profiles.py" },
    ],
    ...(asOf ? { asOf } : {}),
  };
}
