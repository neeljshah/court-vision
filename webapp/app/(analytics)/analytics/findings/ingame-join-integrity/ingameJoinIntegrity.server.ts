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
  timing_artifacts_regenerated: string[];
  timing_artifacts_note: string;
  derived_artifacts_under_review: { artifact: string; stale_inputs: string; note: string }[];
  status: "regenerated";
  resolved_by: string;
  resolution_note: string;
};

export type RegeneratedArtifact = {
  artifact: string;
  n_field: string;
  n_before: number;
  n_after: number;
  headline_before: string;
  headline_after: string;
};

export type IngameRegenerationReceipt = {
  version: number;
  measured_on: string;
  revision_published: number;
  method: { summary: string; segmentation_tool: string; checker_tool: string; corpus_after: string };
  segmentation: { per_sport: Record<string, Record<string, number>> };
  checker: { verdict: string };
  artifacts: RegeneratedArtifact[];
  reading: string[];
  status: "regenerated";
};

export type IngameTimingRegenerationReceipt = {
  version: number;
  measured_on: string;
  revision_published: number;
  method: { summary: string; override_env: string; corpus_after: string };
  checker: { verdict: string };
  artifacts: RegeneratedArtifact[];
  reading: string[];
  status: "regenerated";
};

function loadAudit<T>(basename: string): T {
  return JSON.parse(readFileSync(join(process.cwd(), "public", "data", "audits", basename), "utf8")) as T;
}

/** Loads the committed incident receipt only while rendering the static export. */
export function loadIngameIntegrityReceipt(): IngameIntegrityReceipt {
  return loadAudit<IngameIntegrityReceipt>("mlb-ingame-integrity.json");
}

/** Loads the committed revision-2 regeneration receipt for the before/after table. */
export function loadIngameRegenerationReceipt(): IngameRegenerationReceipt {
  return loadAudit<IngameRegenerationReceipt>("mlb-ingame-regeneration.json");
}

/** Loads the committed revision-2 receipt for the six timing artifacts. */
export function loadIngameTimingRegenerationReceipt(): IngameTimingRegenerationReceipt {
  return loadAudit<IngameTimingRegenerationReceipt>("mlb-ingame-timing-regeneration.json");
}
