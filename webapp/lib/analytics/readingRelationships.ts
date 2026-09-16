export type PopulationInput = {
  id: string;
  sport: string;
  source?: string;
};

// Population is an editorial property, not a sport shortcut. Entries without a
// named entity type retain their source-specific identifier, so they cannot be
// described as the same population by accident.
const entityTypeById: Record<string, string> = {
  calibration_stability: "calibration bins",
  murphy_decomposition: "calibration bins",
  calibration_by_market_type: "calibration bins",
  brier_skill_scores: "game-state cells",
  residual_autocorrelation: "game-state cells",
  ess_ledger: "game-state cells",
  pitch_sequencing: "pitch types",
  statcast_showcase: "pitch types",
  mlb_count_leverage: "game-state cells",
  atlas_mlb_batters_manifest: "batters",
  atlas_mlb_pitch_manifest: "pitch types",
  atlas_nba_manifest: "players",
  atlas_nba_teams_manifest: "teams",
  atlas_soccer_manifest: "teams",
  atlas_tennis_manifest: "players",
  on_off_showcase: "players",
  ctx_player_splits: "players",
  ctx_team_states: "teams",
  nba_matchup_grid: "teams",
  soccer_home_advantage: "teams",
  soccer_form_stability: "teams",
  tennis_surface_transfer: "players",
};

const entityTypeByAnalysis: Record<string, string> = {
  "mlb-batter-atlas-measurements": "batters",
  "mlb-batter-p90-minus-mean-exit-velocity": "batters",
  "mlb-velocity-shape": "pitch types",
  "mlb-pitch-mix-concentration": "pitch types",
  "mlb-count-contrast": "game-state cells",
  "nba-player-atlas-measurements": "players",
  "nba-team-atlas-measurements": "teams",
  "nba-on-off-net-rating-by-player": "players",
  "calibration-by-game-checkpoint": "calibration bins",
  "brier-skill-score-by-game-phase": "game-state cells",
  "cluster-interval-width": "calibration bins",
  "calibration-support-concentration": "calibration bins",
};

function entityType(input: PopulationInput): string {
  return entityTypeByAnalysis[input.id]
    || entityTypeById[input.id]
    || (input.source && entityTypeById[input.source])
    || `source:${input.source || input.id}`;
}

export function populationIdentifier(input: PopulationInput): string {
  return `${input.sport} ${entityType(input)}`;
}

// This small authored graph is the only source of prerequisite labels. Do not
// infer prerequisite order from shared words, shared sport, or source files.
export const AUTHORED_PREREQUISITES: Readonly<Record<string, readonly string[]>> = {
  calibration: ["reliability"],
  "observation-dependence": ["effective-sample-size"],
  murphy_decomposition: ["calibration-by-game-checkpoint"],
  pitch_sequencing: ["mlb-velocity-shape", "mlb-pitch-mix-concentration"],
};

export function isAuthoredPrerequisite(fromId: string, toId: string): boolean {
  return AUTHORED_PREREQUISITES[fromId]?.includes(toId) || false;
}
