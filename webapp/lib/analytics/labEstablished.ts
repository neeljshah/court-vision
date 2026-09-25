import type { LabDataset } from "./labTypes";
import { field as f, labRows, snapshot, type SourceRow } from "./labHelpers";
import { getSoccerVenueLabDataset } from "./labSoccerVenue";
import { getPitchProfilesLabDataset } from "./labPitchProfiles";
import { getLineupSynergyLabDataset } from "./labLineupSynergy";
export function establishedDatasets(): LabDataset[] {
  const output: LabDataset[] = [];
  output.push(getPitchProfilesLabDataset());
  const consistent = snapshot<{ most_consistent_top15: SourceRow[]; least_consistent_top15: SourceRow[] }>("nba_consistency_profiles");
  const consistencyFields = [f("composite_cv_shrunk", "Composite variability", "number", 4), f("pts_per36_mean", "Points / 36"), f("pts_cv_shrunk", "Points variability", "number", 4), f("reb_cv_shrunk", "Rebound variability", "number", 4), f("ast_cv_shrunk", "Assist variability", "number", 4), f("games", "Games", "number", 0)];
  output.push({ id: "nba-consistency", title: "Player consistency", sport: "nba", category: "Player & team", source: "nba_consistency_profiles", description: "Explore how much a player's per-36 production varies from game to game.", scope: "Published extremes from 579 eligible players; 2023-24 through 2025-26.", caveat: "These are the 15 lowest and 15 highest published variability profiles, not the complete player population. Lower variability is not higher skill. Small means can inflate CV.", status: "Descriptive", fields: consistencyFields, rows: [...labRows(consistent.most_consistent_top15, consistencyFields, "player_name", "Most consistent"), ...labRows(consistent.least_consistent_top15, consistencyFields, "player_name", "Least consistent")] });
  output.push(getLineupSynergyLabDataset());
  const rim = snapshot<{ seasons: { season: string; leaders: SourceRow[]; n_qualified: number }[] }>("rim_deterrence");
  const rimFields = [f("delta", "On-minus-off rim share", "pp"), f("rim_share_allowed_on", "Opponent rim share: on", "percent"), f("rim_share_allowed_off", "Opponent rim share: off", "percent"), f("rim_efg_delta", "Rim eFG difference", "pp"), f("min_on", "On-court minutes")];
  output.push({ id: "rim-deterrence", title: "Who changes the shot profile?", sport: "nba", category: "Player & team", source: "rim_deterrence", description: "Inspect opponent rim-attempt shares with a defender on and off the floor.", scope: "Published season leaderboards; 500-minute on-court floor.", caveat: "Negative on-minus-off means fewer rim attempts. This is a selected leaderboard, with teammate, opponent and roster confounds; not an isolated defensive impact estimate.", status: "Descriptive", fields: rimFields, rows: rim.seasons.flatMap(s => labRows(s.leaders, rimFields, "player_name", s.season).map(row => ({ ...row, definition: { sport: "NBA", season: s.season } }))) });
  output.push(getSoccerVenueLabDataset());
  const tennis = snapshot<{ combos: Record<string, { n_players_in_snapshot?: number; clay_hard_gap: { most_clay_favoring?: SourceRow[]; most_hard_favoring?: SourceRow[]; n_qualifying?: number; floor?: string; note?: string }; grass_adaptability: { most_adaptive?: SourceRow[]; least_adaptive?: SourceRow[]; n_qualifying?: number; floor?: string; note?: string } }> }>("tennis_surface_transfer");
  const clayFields = [f("clay_minus_hard", "Clay-minus-hard win rate", "pp"), f("clay_wr", "Clay win rate", "percent"), f("hard_wr", "Hard win rate", "percent"), f("clay_n", "Clay matches", "number", 0), f("hard_n", "Hard matches", "number", 0)];
  const grassFields = [f("grass_adapt", "Grass-minus-overall win rate", "pp"), f("grass_wr", "Grass win rate", "percent"), f("ov_wr", "Overall win rate", "percent"), f("grass_n", "Grass matches", "number", 0)];
  for (const [key, combo] of Object.entries(tennis.combos)) {
    const title = key.replace(/_/g, " ").replace(/atp/g, "ATP").replace(/wta/g, "WTA");
    for (const kind of ["clay", "grass"] as const) {
      const fields = kind === "clay" ? clayFields : grassFields;
      const c = combo.clay_hard_gap; const g = combo.grass_adaptability;
      const rows = kind === "clay" ? [...(c?.most_clay_favoring || []), ...(c?.most_hard_favoring || [])] : [...(g?.most_adaptive || []), ...(g?.least_adaptive || [])];
      const measure = kind === "clay" ? c : g;
      output.push({ id: `tennis-${key}-${kind}`, title: `${title}: ${kind === "clay" ? "clay vs. hard" : "grass adaptation"}`, sport: "tennis", category: "Surface analysis", source: "tennis_surface_transfer", description: "Compare published surface-rate extremes and the match counts behind them.", scope: `${title}; ${kind === "clay" ? "25 matches on each surface" : "15 grass matches"} minimum. Published extremes only.`, caveat: "Opponent strength and draws are uncontrolled. Career means the source's collected history. Empty WTA views indicate no published qualifiers, not a zero effect.", status: rows.length ? "Descriptive" : "No qualifying rows", fields, rows: labRows(rows, fields, "player_name", title), eligiblePopulation: combo.n_players_in_snapshot, qualificationRule: measure?.floor, nQualifying: measure?.n_qualifying, note: measure?.note });
    }
  }
  return output;
}
