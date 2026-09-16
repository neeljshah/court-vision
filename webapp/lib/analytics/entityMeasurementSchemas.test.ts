import { describe, expect, it } from "vitest";
import { getEntityMeasurementSchema } from "./entityMeasurementSchemas";

describe("entity measurement schemas", () => {
  it("selects the pitch-type fields for Changeup", () => {
    expect(getEntityMeasurementSchema("mlb_pitch", { entity: "pitch_type:CH" })).toMatchObject({
      cohort: "MLB pitch types", fields: expect.arrayContaining(["velo_p50", "count_state_pct"]),
    });
  });

  it("selects the team fields for Athletics", () => {
    expect(getEntityMeasurementSchema("mlb_pitch", { entity: "team:ATH" })).toMatchObject({
      cohort: "MLB pitching teams", fields: expect.arrayContaining(["n_pitch_types_used", "velo_percentiles_by_type"]),
    });
  });

  it("selects the count-state fields", () => {
    expect(getEntityMeasurementSchema("mlb_pitch", { entity: "count:0-0" })).toMatchObject({
      cohort: "MLB count states", fields: expect.arrayContaining(["balls", "strikes"]),
    });
  });

  it("selects probability-band fields by calibration card type", () => {
    expect(getEntityMeasurementSchema("calibration", { card_type: "prob_band" })).toMatchObject({
      cohort: "calibration probability bands", fields: expect.arrayContaining(["by_time_bucket", "mean_y_overall"]),
    });
  });
});
