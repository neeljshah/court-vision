import { describe, expect, it } from "vitest";
import { snapshot } from "./labHelpers";
import { buildCalibrationCheckpointResearch, calibrationCards, type CalibrationManifest } from "./researchCalibrationCheckpoints";

const manifest = snapshot<CalibrationManifest>("atlas_calibration_manifest");
const entries = manifest.entries || [];
const checkpoints = entries.filter(entry => entry.card_type === "time_checkpoint");
const analysis = buildCalibrationCheckpointResearch(manifest);

describe("calibration checkpoint research", () => {
  it("keeps published checkpoint values and names the signed ECE subtraction", () => {
    const analysis = buildCalibrationCheckpointResearch({ entries: [{
      entity: "mlb inning 1", card_path: "mlb_inning_1.png", sport: "mlb", card_type: "time_checkpoint",
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
      entity: "soccer minute 60", card_path: "soccer_60.png", sport: "soccer", card_type: "time_checkpoint",
      key_numbers: { n: 40, model_ece: null, market_ece: 0.1 },
    }] });
    expect(analysis.rows[0].values).toMatchObject({ model_ece: null, market_ece: 0.1, ece_gap_model_minus_market: null, n: 40 });
  });

  it("drops a card that is not a published time checkpoint", () => {
    const analysis = buildCalibrationCheckpointResearch({ entries: [
      { entity: "mlb inning 1", card_path: "mlb_inning_1.png", sport: "mlb", card_type: "time_checkpoint", key_numbers: { n: 100, model_ece: 0.12, market_ece: 0.08 } },
      { entity: "mlb band 0-.2", card_path: "mlb_band_0_2.png", sport: "mlb", card_type: "prob_band", key_numbers: { n: 10, mean_y_overall: 0.2, band_reference: 0.1, n_time_buckets_with_data: 3 } },
    ] });
    expect(analysis.rows.map(row => row.id)).toEqual(["calibration-checkpoint-mlb_inning_1"]);
  });
});

describe("calibration by game checkpoint", () => {
  it("keeps only the published time-checkpoint cards", () => {
    expect(checkpoints.length).toBeGreaterThan(0);
    expect(checkpoints).toHaveLength(16);
    expect(analysis.rows).toHaveLength(checkpoints.length);
    expect(analysis.rows).toHaveLength(entries.length - entries.filter(entry => entry.card_type === "prob_band").length);
    expect(analysis.scope).toContain(String(checkpoints.length));
  });

  it("carries no probability-band row", () => {
    const bandNames = new Set(entries.filter(entry => entry.card_type === "prob_band").map(entry => String(entry.entity)));
    expect(bandNames.size).toBeGreaterThan(0);
    for (const row of analysis.rows) expect([...bandNames].some(name => row.label.includes(name))).toBe(false);
    expect(analysis.rows.every(row => /inning|minute/.test(row.label))).toBe(true);
  });

  it("publishes a calibration error on every row", () => {
    for (const row of analysis.rows) {
      expect(typeof row.values.model_ece).toBe("number");
      expect(typeof row.values.market_ece).toBe("number");
      expect(typeof row.values.ece_gap_model_minus_market).toBe("number");
    }
  });

  it("points every row at its own published manifest entry", () => {
    for (const { slug, entry, index } of calibrationCards(manifest, "time_checkpoint")) {
      const row = analysis.rows.find(candidate => candidate.id === `calibration-checkpoint-${slug}`)!;
      expect(row.href).toBe(`/analytics/players/calibration/${slug}`);
      expect(row.sourcePaths).toContain(`entries[${index}].key_numbers.model_ece`);
      expect(entries[index]).toBe(entry);
    }
  });
});
