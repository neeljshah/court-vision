export type PopulationInput = {
  id: string;
  sport: string;
  source?: string;
  populationId?: string;
};

// Population identity is editorial metadata. A common sport or source file is
// not enough to say that two readings describe the same observed population.
const SOURCE_POPULATION_IDS: Readonly<Record<string, string>> = {
  atlas_mlb_batters_manifest: "mlb_batters",
  atlas_mlb_pitch_manifest: "mlb_pitch_types",
  atlas_nba_manifest: "nba_players",
  atlas_nba_teams_manifest: "nba_teams",
  atlas_soccer_manifest: "soccer_teams",
  atlas_tennis_manifest: "tennis_players",
  calibration_by_market_type: "cross_sport_calibration_score_rows",
  calibration_stability: "cross_sport_calibration_bins",
  ess_ledger: "cross_sport_game_state_cells",
  mlb_count_leverage: "mlb_count_states",
  murphy_decomposition: "cross_sport_score_decomposition_rows",
  pitch_sequencing: "mlb_pitch_sequences",
  residual_anatomy: "nba_game_state_residual_rows",
  residual_autocorrelation: "cross_sport_residual_series",
  statcast_showcase: "mlb_pitch_types",
  blowout_dynamics: "nba_games",
  why_attribution: "nba_state_contrasts",
};

// These analyses intentionally share a named population with another reading.
// All other analyses receive their own stable identifier below, which prevents
// a shared source file from becoming a false same-population recommendation.
const ANALYSIS_POPULATION_IDS: Readonly<Record<string, string>> = {
  "calibration-by-game-checkpoint": "cross_sport_calibration_bins",
  "calibration-support-concentration": "cross_sport_calibration_bins",
  "cluster-interval-width": "cross_sport_calibration_bins",
  "mlb-pitch-mix-concentration": "mlb_pitch_types",
  "mlb-velocity-band-concentration": "mlb_pitch_types",
  "mlb-velocity-shape": "mlb_pitch_types",
  "nba-on-off-net-rating-by-player": "nba_players",
  "nba-player-atlas-measurements": "nba_players",
  "nba-team-atlas-measurements": "nba_teams",
  "signed-calibration-direction": "cross_sport_calibration_bins",
};

export function populationIdentifier(input: PopulationInput): string {
  if (input.populationId) return input.populationId;
  if (ANALYSIS_POPULATION_IDS[input.id]) return ANALYSIS_POPULATION_IDS[input.id];
  if (input.source && SOURCE_POPULATION_IDS[input.source]) return SOURCE_POPULATION_IDS[input.source];
  if (SOURCE_POPULATION_IDS[input.id]) return SOURCE_POPULATION_IDS[input.id];
  return input.source ? `analysis:${input.id}` : `entry:${input.id}`;
}

// This small authored graph is the only source of prerequisite labels. Do not
// infer prerequisite order from shared words, shared sport, or source files.
export const AUTHORED_PREREQUISITES: Readonly<Record<string, readonly string[]>> = {
  calibration: ["reliability"],
  "observation-dependence": ["effective-sample-size"],
  "score-decomposition": ["calibration"],
  "pitch-sequencing": ["mlb-velocity-shape", "mlb-pitch-mix-concentration"],
  "residual-anatomy": ["observation-dependence"],
  "blowout-timing": ["comeback-rates-deficit-time"],
  "state-contrasts": ["blowout-timing"],
};

export function isAuthoredPrerequisite(fromId: string, toId: string): boolean {
  return AUTHORED_PREREQUISITES[fromId]?.includes(toId) || false;
}
