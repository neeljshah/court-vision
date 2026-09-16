import { readFileSync } from "node:fs";
import { join } from "node:path";

export type Agreement = { n: number; frequency: number };
export type SportIntegrityCounts = {
  files: number;
  ticks: number;
  mixed_files: number;
  stateless_ticks: number;
  truncated_games: number;
  label_disagreements: number;
  mismatched_ticks?: number;
  label_disagreement_note?: string;
  leader_wins_last_tick?: { games: number; frequency: number };
  late_inning_leader_agreement?: { all_ticks: Agreement; final_segment: Agreement };
};

export type IngameIntegrityReceipt = {
  version: number;
  measured_on: string;
  method: string;
  definitions: Record<string, string>;
  per_sport: { mlb: SportIntegrityCounts; soccer_intl: SportIntegrityCounts };
  exposed_artifacts: string[];
  timing_artifacts_under_review: string[];
  timing_artifacts_note: string;
  status: "withdrawn-pending-regeneration";
};

/** Loads the committed incident receipt only while rendering the static export. */
export function loadIngameIntegrityReceipt(): IngameIntegrityReceipt {
  const path = join(process.cwd(), "public", "data", "audits", "mlb-ingame-integrity.json");
  return JSON.parse(readFileSync(path, "utf8")) as IngameIntegrityReceipt;
}
