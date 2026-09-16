import { describe, expect, it } from "vitest";
import { buildCalibrationCheckpointResearch } from "./researchCalibrationCheckpoints";

describe("calibration checkpoint research", () => {
  it("keeps published checkpoint values and names the signed ECE subtraction", () => {
    const analysis = buildCalibrationCheckpointResearch({ entries: [{
      entity: "mlb inning 1", card_path: "mlb_inning_1.png", sport: "mlb",
      key_numbers: { n: 100, model_ece: 0.12, market_ece: 0.08 }, floors: "n>=30", as_of: "2026-01-02T00:00:00Z",
    }] });
    expect(analysis.rows[0]).toMatchObject({
      label: "MLB | mlb inning 1", href: "/analytics/players/calibration/mlb_inning_1",
      values: { n: 100, model_ece: 0.12, market_ece: 0.08, ece_gap_model_minus_market: 0.04 },
    });
    expect(analysis.formula).toContain("model_ece - published market_ece");
  });

  it("preserves an unavailable calibration operand and its derived gap", () => {
    const analysis = buildCalibrationCheckpointResearch({ entries: [{
      entity: "soccer minute 60", card_path: "soccer_60.png", sport: "soccer",
      key_numbers: { n: 40, model_ece: null, market_ece: 0.1 },
    }] });
    expect(analysis.rows[0].values).toMatchObject({ model_ece: null, market_ece: 0.1, ece_gap_model_minus_market: null, n: 40 });
  });
});
