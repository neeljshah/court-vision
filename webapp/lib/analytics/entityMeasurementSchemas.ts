import { atlasPackFieldDefinitions } from "./atlasFieldDefinitions";

export type EntitySchemaEntry = { entity?: string; card_type?: string };
export type EntityMeasurementSchema = { cohort: string; fields: string[] };

const MLB_PITCH_FIELDS: Record<string, EntityMeasurementSchema> = {
  pitch_type: { cohort: "MLB pitch types", fields: ["n_pitches", "pct_of_all_pitches", "velo_p10", "velo_p50", "velo_p90", "count_leverage_pct", "count_state_pct", "outcome_mix_pct"] },
  team: { cohort: "MLB pitching teams", fields: ["n_pitches", "n_pitch_types_used", "top_pitch_type", "top_pitch_type_pct", "outcome_mix_pct", "velo_percentiles_by_type"] },
  count: { cohort: "MLB count states", fields: ["balls", "strikes", "n_pitches", "pct_of_all_pitches", "top_pitch_type", "top_pitch_type_pct", "outcome_mix_pct"] },
};

const CALIBRATION_FIELDS: Record<string, EntityMeasurementSchema> = {
  time_checkpoint: { cohort: "calibration time checkpoints", fields: ["n", "model_ece", "market_ece"] },
  prob_band: { cohort: "calibration probability bands", fields: ["n", "mean_y_overall", "band_reference", "n_time_buckets_with_data", "by_time_bucket"] },
};

function prefix(entity?: string): string | undefined {
  return entity?.split(":", 1)[0];
}

function packSchema(pack: string): EntityMeasurementSchema {
  return {
    cohort: pack.replace(/_/g, " "),
    fields: atlasPackFieldDefinitions(pack).map((field) => field.key),
  };
}

export function getEntityMeasurementSchema(pack: string, entry: EntitySchemaEntry): EntityMeasurementSchema {
  if (pack === "mlb_pitch") return MLB_PITCH_FIELDS[prefix(entry.entity) || ""] || packSchema(pack);
  if (pack === "calibration") return CALIBRATION_FIELDS[entry.card_type || ""] || packSchema(pack);
  return packSchema(pack);
}
