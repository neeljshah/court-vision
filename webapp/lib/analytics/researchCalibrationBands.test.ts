import { describe, expect, it } from "vitest";
import { snapshot } from "./labHelpers";
import { buildCalibrationBandResearch } from "./researchCalibrationBands";
import { calibrationCards, type CalibrationManifest } from "./researchCalibrationCheckpoints";

const manifest = snapshot<CalibrationManifest>("atlas_calibration_manifest");
const entries = manifest.entries || [];
const bands = entries.filter(entry => entry.card_type === "prob_band");
const analysis = buildCalibrationBandResearch(manifest);
const fieldKeys = analysis.fields.map(field => field.key);
const reference = analysis.fields.find(field => field.key === "band_reference")!;

describe("calibration by published probability band", () => {
  it("keeps only the published probability-band cards", () => {
    expect(bands).toHaveLength(10);
    expect(analysis.rows).toHaveLength(bands.length);
    expect(analysis.scope).toContain(String(bands.length));
    expect(analysis.rows.every(row => /band/.test(row.label))).toBe(true);
  });

  it("publishes the band fields and no calibration error", () => {
    expect(fieldKeys).toEqual(["mean_y_overall", "band_reference", "n", "n_time_buckets_with_data"]);
    for (const row of analysis.rows) for (const key of fieldKeys) expect(typeof row.values[key]).toBe("number");
    expect(fieldKeys.some(key => key.includes("ece"))).toBe(false);
  });

  it("labels the band reference as a reference, not as a forecast", () => {
    expect(reference.label).toBe("Published band reference");
    expect(reference.label).not.toMatch(/forecast|probability/i);
    expect(analysis.interpretation).toContain("not a mean probability produced by a model or a market");
  });

  it("links every band to the card that publishes its time-bucket detail", () => {
    expect(analysis.interpretation).toContain("by_time_bucket");
    for (const { slug, entry, index } of calibrationCards(manifest, "prob_band")) {
      const row = analysis.rows.find(candidate => candidate.id === `calibration-band-${slug}`)!;
      expect(row.href).toBe(`/analytics/players/calibration/${slug}`);
      expect(row.sourcePaths).toContain(`entries[${index}].key_numbers.n_time_buckets_with_data`);
      expect(Array.isArray(entry.key_numbers.by_time_bucket)).toBe(true);
      expect(row.values.n_time_buckets_with_data).toBe(entry.key_numbers.n_time_buckets_with_data);
    }
  });
});
