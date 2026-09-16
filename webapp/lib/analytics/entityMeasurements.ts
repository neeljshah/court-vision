export type EntityEntry = { key_numbers: Record<string, unknown>; floors?: string };
export type EntityPercentilePack = {
  n_in_pack: number;
  fields: Record<string, { n_ranked: number }>;
  entities: Record<string, Record<string, number>>;
};
export type ScalarMeasurement = {
  key: string; label: string; value: string; unit?: string; percentile?: number; nRanked?: number;
};
export type Distribution = { key: string; label: string; rows: Array<{ key: string; share: number }> };
export type UnavailableMeasurement = { key: string; label: string; floor?: string };
export type EntityMeasurements = { scalars: ScalarMeasurement[]; distributions: Distribution[]; unavailable: UnavailableMeasurement[] };

const FIELDS: Record<string, string[]> = {
  nba_players: ["seasons_played", "career_games", "career_minutes", "career_pts_per36", "career_reb_per36", "career_ast_per36", "career_fg_pct", "career_fg3_pct", "career_ft_pct"],
  nba_teams: ["seasons_covered", "games_total", "ppg_latest_season", "pace_proxy_latest_season", "top_contributor", "top_contributor_pra_per36", "top_contributor_minutes"],
  mlb_batters: ["bats", "switch_hitter", "pitches_faced", "top_pitch_type_seen", "top_pitch_type_seen_pct", "velo_seen_p10", "velo_seen_p50", "velo_seen_p90", "pct_pitches_in_rulebook_zone", "n_batted_balls", "avg_exit_velo", "exit_velo_p90", "avg_estimated_woba_on_contact"],
  mlb_pitch: ["n_pitches", "pct_of_all_pitches", "velo_p10", "velo_p50", "velo_p90", "count_leverage_pct", "count_state_pct", "outcome_mix_pct"],
  soccer: ["ppg_l10", "ppg_home_l10", "ppg_away_l10", "gf_l10", "ga_l10", "gd_l10", "winrate_l10", "clean_sheet_rate_l10", "clean_sheet_rate_season", "clean_sheet_rate_home", "clean_sheet_rate_away"],
  tennis: ["hard_wr_career", "clay_wr_career", "grass_wr_career", "hard_wr_recent", "clay_wr_recent", "grass_wr_recent", "clay_minus_hard_career", "clay_minus_hard_recent", "grass_adapt_career", "grass_adapt_recent"],
  calibration: ["n", "model_ece", "market_ece"],
};

export function measurementLabel(key: string): string {
  return key.replace(/^career_/, "").replace(/_/g, " ").replace(/\bpct\b/g, "%")
    .replace(/per36/g, "/36").replace(/\bfg3\b/g, "3P").replace(/\bfg\b/g, "FG")
    .replace(/\bft\b/g, "FT").replace(/\bpts\b/g, "PTS").replace(/\breb\b/g, "REB")
    .replace(/\bast\b/g, "AST").trim();
}

function isRate(key: string, value: number): boolean {
  return /(^|_)(pct|wr|winrate|clean_sheet_rate)(_|$)/.test(key) || (/rate/.test(key) && value >= 0 && value <= 1);
}
function formatted(key: string, value: string | number | boolean): { value: string; unit?: string } {
  if (typeof value === "boolean") return { value: value ? "yes" : "no" };
  if (typeof value === "string") return { value };
  if (isRate(key, value)) return { value: `${(value <= 1 ? value * 100 : value).toFixed(1)}%`, unit: "%" };
  return { value: Number.isInteger(value) ? String(value) : String(Number(value.toFixed(3))) };
}
function floorFor(key: string, floors?: string): string | undefined {
  if (!floors) return undefined;
  const root = key.replace(/_(career|recent)$/, "");
  return floors.split("|").map((part) => part.trim()).find((part) => part.startsWith(`${root}:`));
}

export function entityMeasurements(
  pack: string, entry: EntityEntry, slug: string, percentilePack?: EntityPercentilePack | null,
): EntityMeasurements {
  const expected = FIELDS[pack] || [];
  const ranks = percentilePack?.entities[slug] || {};
  const scalars: ScalarMeasurement[] = [];
  const distributions: Distribution[] = [];
  const unavailable: UnavailableMeasurement[] = [];
  for (const key of expected) {
    const value = entry.key_numbers[key];
    if (value === null || value === undefined) {
      unavailable.push({ key, label: measurementLabel(key), floor: floorFor(key, entry.floors) });
    } else if (value && typeof value === "object" && /_pct$/.test(key)) {
      const rows = Object.entries(value).filter((row): row is [string, number] => typeof row[1] === "number").map(([rowKey, share]) => ({ key: rowKey, share }));
      if (rows.length) distributions.push({ key, label: measurementLabel(key), rows });
    } else if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
      const display = formatted(key, value);
      scalars.push({ key, label: measurementLabel(key), ...display, percentile: ranks[key], nRanked: percentilePack?.fields[key]?.n_ranked });
    }
  }
  return { scalars, distributions, unavailable };
}
