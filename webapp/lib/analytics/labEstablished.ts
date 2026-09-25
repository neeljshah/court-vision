import type { LabDataset } from "./labTypes";
import { field as f, labRows, snapshot, type SourceRow } from "./labHelpers";
import { getSoccerVenueLabDataset } from "./labSoccerVenue";
import { getPitchProfilesLabDataset } from "./labPitchProfiles";
import { getLineupSynergyLabDataset } from "./labLineupSynergy";
import { getRimProfileLabDataset } from "./labRimProfile";
import { getNbaConsistencyLabDataset } from "./labNbaConsistency";
export function establishedDatasets(): LabDataset[] {
  const output: LabDataset[] = [];
  output.push(getPitchProfilesLabDataset());
  output.push(getNbaConsistencyLabDataset());
  output.push(getLineupSynergyLabDataset());
  output.push(getRimProfileLabDataset());
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
