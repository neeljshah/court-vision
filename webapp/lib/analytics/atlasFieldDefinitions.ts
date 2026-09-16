export type AtlasFieldUnit =
  | "percent-already" | "fraction-as-percent" | "per36" | "minutes"
  | "games" | "count" | "rate" | "mph" | "index" | "text" | "number";

export type AtlasFieldDefinition = {
  key: string;
  label: string;
  unit: AtlasFieldUnit;
  decimals: number;
  isIdentifier?: boolean;
  isDifference?: boolean;
};

const definition = (key: string, label: string, unit: AtlasFieldUnit, decimals: number, extra?: Pick<AtlasFieldDefinition, "isIdentifier" | "isDifference">): AtlasFieldDefinition => ({ key, label, unit, decimals, ...extra });

const humanize = (key: string) => key.replace(/_/g, " ").replace(/\b\w/g, letter => letter.toUpperCase());

export const ATLAS_FIELD_DEFINITIONS: Record<string, Record<string, AtlasFieldDefinition>> = {
  calibration: {
    band_reference: definition("band_reference", "Calibration band reference", "text", 0),
    by_time_bucket: definition("by_time_bucket", "Calibration by time bucket", "text", 0),
    market_ece: definition("market_ece", "Market expected calibration error", "index", 4),
    mean_y_overall: definition("mean_y_overall", "Observed outcome mean, overall", "rate", 4),
    model_ece: definition("model_ece", "Model expected calibration error", "index", 4),
    n: definition("n", "Published observations", "count", 0),
    n_time_buckets_with_data: definition("n_time_buckets_with_data", "Time buckets with data", "count", 0),
  },
  mlb_batters: {
    avg_estimated_woba_on_contact: definition("avg_estimated_woba_on_contact", "Estimated wOBA on contact, average", "rate", 3),
    avg_exit_velo: definition("avg_exit_velo", "Exit velocity, average", "mph", 1),
    bats: definition("bats", "Batting side", "text", 0),
    batter_id: definition("batter_id", "Batter identifier", "text", 0, { isIdentifier: true }),
    exit_velo_p90: definition("exit_velo_p90", "Exit velocity, 90th percentile", "mph", 1),
    n_batted_balls: definition("n_batted_balls", "Batted-ball events", "count", 0),
    pct_pitches_in_rulebook_zone: definition("pct_pitches_in_rulebook_zone", "Pitches in the rulebook zone", "percent-already", 1),
    pitches_faced: definition("pitches_faced", "Pitches faced", "count", 0),
    switch_hitter: definition("switch_hitter", "Switch hitter", "text", 0),
    top_pitch_type_seen: definition("top_pitch_type_seen", "Most-seen pitch type", "text", 0),
    top_pitch_type_seen_pct: definition("top_pitch_type_seen_pct", "Most-seen pitch type share", "percent-already", 1),
    velo_seen_p10: definition("velo_seen_p10", "Velocity seen, 10th percentile", "mph", 1),
    velo_seen_p50: definition("velo_seen_p50", "Velocity seen, median", "mph", 1),
    velo_seen_p90: definition("velo_seen_p90", "Velocity seen, 90th percentile", "mph", 1),
  },
  mlb_pitch: {
    balls: definition("balls", "Balls in count", "count", 0),
    count_leverage_pct: definition("count_leverage_pct", "Pitch share by count leverage", "percent-already", 1),
    count_state_pct: definition("count_state_pct", "Pitch share by count state", "percent-already", 1),
    n_pitch_types_used: definition("n_pitch_types_used", "Pitch types used", "count", 0),
    n_pitches: definition("n_pitches", "Pitches thrown", "count", 0),
    outcome_mix_pct: definition("outcome_mix_pct", "Pitch outcome mix", "percent-already", 1),
    pct_of_all_pitches: definition("pct_of_all_pitches", "Share of all pitches", "percent-already", 2),
    strikes: definition("strikes", "Strikes in count", "count", 0),
    top_pitch_type: definition("top_pitch_type", "Most common pitch type", "text", 0),
    top_pitch_type_pct: definition("top_pitch_type_pct", "Most common pitch type share", "percent-already", 1),
    velo_p10: definition("velo_p10", "Velocity, 10th percentile", "mph", 1),
    velo_p50: definition("velo_p50", "Velocity, median", "mph", 1),
    velo_p90: definition("velo_p90", "Velocity, 90th percentile", "mph", 1),
    velo_percentiles_by_type: definition("velo_percentiles_by_type", "Velocity percentiles by pitch type", "text", 0),
  },
  nba_players: {
    career_ast_per36: definition("career_ast_per36", "Assists per 36 minutes, career", "per36", 1),
    career_fg_pct: definition("career_fg_pct", "Field-goal percentage, career", "percent-already", 1),
    career_fg3_pct: definition("career_fg3_pct", "Three-point percentage, career", "percent-already", 1),
    career_ft_pct: definition("career_ft_pct", "Free-throw percentage, career", "percent-already", 1),
    career_games: definition("career_games", "Games played, career", "games", 0),
    career_minutes: definition("career_minutes", "Minutes played, career", "minutes", 1),
    career_pts_per36: definition("career_pts_per36", "Points per 36 minutes, career", "per36", 1),
    career_reb_per36: definition("career_reb_per36", "Rebounds per 36 minutes, career", "per36", 1),
    player_id: definition("player_id", "Player identifier", "text", 0, { isIdentifier: true }),
    seasons_played: definition("seasons_played", "Seasons played", "count", 0),
  },
  nba_teams: {
    games_total: definition("games_total", "Games covered", "games", 0),
    pace_proxy_latest_season: definition("pace_proxy_latest_season", "Pace proxy, latest season", "rate", 1),
    ppg_latest_season: definition("ppg_latest_season", "Points per game, latest season", "rate", 1),
    seasons_covered: definition("seasons_covered", "Seasons covered", "count", 0),
    team_full_name: definition("team_full_name", "Team", "text", 0),
    top_contributor: definition("top_contributor", "Top contributor", "text", 0),
    top_contributor_minutes: definition("top_contributor_minutes", "Top contributor minutes", "minutes", 1),
    top_contributor_pra_per36: definition("top_contributor_pra_per36", "Top contributor PRA per 36 minutes", "per36", 1),
  },
  soccer: {
    clean_sheet_rate_away: definition("clean_sheet_rate_away", "Clean-sheet rate, away matches", "fraction-as-percent", 1),
    clean_sheet_rate_home: definition("clean_sheet_rate_home", "Clean-sheet rate, home matches", "fraction-as-percent", 1),
    clean_sheet_rate_l10: definition("clean_sheet_rate_l10", "Clean-sheet rate, last 10 matches", "fraction-as-percent", 1),
    clean_sheet_rate_season: definition("clean_sheet_rate_season", "Clean-sheet rate, season", "fraction-as-percent", 1),
    ga_l10: definition("ga_l10", "Goals against per game, last 10 matches", "rate", 2),
    gd_l10: definition("gd_l10", "Goal difference per game, last 10 matches", "rate", 2),
    gf_l10: definition("gf_l10", "Goals for per game, last 10 matches", "rate", 2),
    ppg_away_l10: definition("ppg_away_l10", "Points per game, away matches in last 10", "rate", 2),
    ppg_home_l10: definition("ppg_home_l10", "Points per game, home matches in last 10", "rate", 2),
    ppg_l10: definition("ppg_l10", "Points per game, last 10 matches", "rate", 2),
    winrate_l10: definition("winrate_l10", "Win rate, last 10 matches", "fraction-as-percent", 1),
  },
  tennis: {
    clay_minus_hard_career: definition("clay_minus_hard_career", "Clay minus hard-court win rate, career", "fraction-as-percent", 1, { isDifference: true }),
    clay_minus_hard_recent: definition("clay_minus_hard_recent", "Clay minus hard-court win rate, recent", "fraction-as-percent", 1, { isDifference: true }),
    clay_wr_career: definition("clay_wr_career", "Clay-court win rate, career", "fraction-as-percent", 1),
    clay_wr_recent: definition("clay_wr_recent", "Clay-court win rate, recent", "fraction-as-percent", 1),
    grass_adapt_career: definition("grass_adapt_career", "Grass minus hard-court win rate, career", "fraction-as-percent", 1, { isDifference: true }),
    grass_adapt_recent: definition("grass_adapt_recent", "Grass minus hard-court win rate, recent", "fraction-as-percent", 1, { isDifference: true }),
    grass_wr_career: definition("grass_wr_career", "Grass-court win rate, career", "fraction-as-percent", 1),
    grass_wr_recent: definition("grass_wr_recent", "Grass-court win rate, recent", "fraction-as-percent", 1),
    hard_wr_career: definition("hard_wr_career", "Hard-court win rate, career", "fraction-as-percent", 1),
    hard_wr_recent: definition("hard_wr_recent", "Hard-court win rate, recent", "fraction-as-percent", 1),
    player_id: definition("player_id", "Player identifier", "text", 0, { isIdentifier: true }),
  },
};

export function atlasFieldDefinition(pack: string, key: string): AtlasFieldDefinition {
  return ATLAS_FIELD_DEFINITIONS[pack]?.[key] || definition(key, humanize(key), "number", 3, /(^|_)id$/.test(key) ? { isIdentifier: true } : undefined);
}

export function atlasPackFieldDefinitions(pack: string): AtlasFieldDefinition[] {
  return Object.values(ATLAS_FIELD_DEFINITIONS[pack] || {});
}
