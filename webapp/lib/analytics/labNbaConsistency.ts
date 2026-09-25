import { field as f, snapshot } from "./labHelpers";
import type { LabDataset, LabRow } from "./labTypes";

type Entry = Record<string, unknown>;
type Source = {
  as_of?: unknown;
  methodology?: unknown;
  input_coverage?: unknown;
  most_consistent_top15?: unknown;
  least_consistent_top15?: unknown;
};

const object = (value: unknown): value is Entry => value !== null && typeof value === "object" && !Array.isArray(value);
const finite = (value: unknown): number | null => typeof value === "number" && Number.isFinite(value) ? value : null;
const count = (value: unknown): number | null => typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null;
const positiveCount = (value: unknown): number | null => {
  const result = count(value);
  return result !== null && result > 0 ? result : null;
};
const positive = (value: unknown): number | null => {
  const result = finite(value);
  return result !== null && result > 0 ? result : null;
};
const nonnegative = (value: unknown): number | null => {
  const result = finite(value);
  return result !== null && result >= 0 ? result : null;
};

function sourceRows(value: unknown, key: "most_consistent_top15" | "least_consistent_top15"): Entry[] {
  if (!Array.isArray(value)) throw new Error(`nba_consistency_profiles.${key} must be an array`);
  value.forEach((row, index) => {
    if (!object(row)) throw new Error(`nba_consistency_profiles.${key}[${index}] must be an object`);
    if (typeof row.player_name !== "string" || !row.player_name.trim()) {
      throw new Error(`nba_consistency_profiles.${key}[${index}].player_name must be a nonempty string`);
    }
  });
  return value as Entry[];
}

export function buildNbaConsistencyLabDataset(source: Source): LabDataset {
  const most = sourceRows(source.most_consistent_top15, "most_consistent_top15");
  const least = sourceRows(source.least_consistent_top15, "least_consistent_top15");
  const method = object(source.methodology) ? source.methodology : {};
  const coverage = object(source.input_coverage) ? source.input_coverage : {};
  const asOf = typeof source.as_of === "string" && source.as_of.trim() ? source.as_of.trim() : "unavailable";
  const seasons = Array.isArray(method.seasons_pooled) && method.seasons_pooled.length > 0 &&
    method.seasons_pooled.every((season: unknown) => typeof season === "string" && season.trim().length > 0)
    ? (method.seasons_pooled as string[]).join(", ") : "pooled seasons unavailable";
  const minutes = nonnegative(method.min_game_minutes_floor);
  const minimumGames = positiveCount(method.min_qualifying_games_floor);
  const shrinkK = positive(method.shrink_k_games);
  const eligible = count(coverage.players_meeting_floor);
  const sourcePlayers = count(coverage.unique_players);
  const fields = [
    f("composite_cv_shrunk", "Composite variability", "number", 4),
    f("pts_per36_mean", "Points / 36"),
    f("pts_cv_shrunk", "Points variability", "number", 4),
    f("reb_cv_shrunk", "Rebound variability", "number", 4),
    f("ast_cv_shrunk", "Assist variability", "number", 4),
    f("games", "Qualifying game appearances", "number", 0),
    f("shrink_weight", "Player-data blend weight", "percent", 1),
  ];
  const rows = (entries: Entry[], key: string, group: string): LabRow[] => entries.map((raw, index) => {
    const weight = finite(raw.shrink_weight);
    const playerId = count(raw.player_id);
    return {
      id: `${group}-${index}`,
      label: (raw.player_name as string).trim(),
      group,
      values: {
        composite_cv_shrunk: finite(raw.composite_cv_shrunk),
        pts_per36_mean: finite(raw.pts_per36_mean),
        pts_cv_shrunk: finite(raw.pts_cv_shrunk),
        reb_cv_shrunk: finite(raw.reb_cv_shrunk),
        ast_cv_shrunk: finite(raw.ast_cv_shrunk),
        games: count(raw.games),
        shrink_weight: weight !== null && weight >= 0 && weight <= 1 ? weight : null,
      },
      note: `Source: nba_consistency_profiles.json ${key}[${index}]. ` +
        `Source player_id: ${playerId === null ? "unavailable" : playerId}. ` +
        "Qualifying game appearances count games meeting the pooled minutes floor, not valid observations for each stat. " +
        "The published player-data blend weight is rounded to three decimals; it is not a confidence, probability, or effectiveness score. " +
        "Per-stat valid counts and raw standard deviations are unavailable in this snapshot.",
    };
  });
  return {
    id: "nba-consistency",
    title: "Player consistency",
    sport: "nba",
    category: "Player & team",
    source: "nba_consistency_profiles",
    description: "Compare published game-to-game variation in per-36 points, rebounds, and assists. Composite variability is the equal mean of their three shrunk coefficients of variation (CVs). Each shrunk CV = w x raw player CV + (1 - w) x qualified league mean CV, with source w = qualifying games / (qualifying games + K). The displayed weight is the published rounded value.",
    scope: `${most.length} most consistent and ${least.length} least consistent published rows from ${eligible === null ? "an unavailable number of" : eligible} eligible players` +
      `${sourcePlayers === null ? " (source player count unavailable)" : ` among ${sourcePlayers} source unique players`}; ` +
      `as of ${asOf}; pooled seasons: ${seasons}. ${minutes === null ? "Qualifying minutes floor unavailable" : `Games qualify with at least ${minutes} minutes played (inclusive)`}; ` +
      `players require ${minimumGames === null ? "an unavailable number of" : `at least ${minimumGames}`} qualifying appearances. ` +
      `Published shrinkage K: ${shrinkK === null ? "unavailable" : `${shrinkK} games`}. This is a dated source snapshot, not complete season coverage.`,
    caveat: "These are published extremes, not the complete player population. Lower CV does not mean higher skill, and low means can inflate CV. Opponent, rest, and role effects are unadjusted. This describes past games and does not forecast future variation. Qualifying appearances are not per-stat valid counts; raw standard deviations cannot be reconstructed from this snapshot.",
    status: most.length + least.length ? "Descriptive" : "No published rows",
    fields,
    rows: [
      ...rows(most, "most_consistent_top15", "Most consistent"),
      ...rows(least, "least_consistent_top15", "Least consistent"),
    ],
    eligiblePopulation: eligible === null ? undefined : eligible,
  };
}

export function getNbaConsistencyLabDataset(): LabDataset {
  return buildNbaConsistencyLabDataset(snapshot<Source>("nba_consistency_profiles"));
}
