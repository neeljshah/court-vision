import { describe, expect, it } from "vitest";
import { buildPitchProfilesLabDataset, getPitchProfilesLabDataset } from "./labPitchProfiles";
import { labComparisonPolicy } from "./labComparisonPolicy";
import { displayMeasurement } from "./labTypes";

describe("pitch profiles lab dataset", () => {
  it("preserves all 19 published mix rows and six existing fields before the two derived fields", () => {
    const dataset = getPitchProfilesLabDataset();
    expect(dataset.id).toBe("pitch-profiles");
    expect(dataset.source).toBe("statcast_showcase");
    expect(dataset.rows).toHaveLength(19);
    expect(dataset.fields.map(field => field.key)).toEqual([
      "p50", "p10", "p90", "pct", "mix_n", "velocity_n", "velocity_span", "velocity_coverage",
    ]);
    expect(dataset.rows.reduce((sum, row) => sum + (row.values.mix_n ?? 0), 0)).toBe(693037);
    expect(dataset.rows.filter(row => row.values.velocity_n !== null)).toHaveLength(16);
    expect(dataset.scope).toContain("693,037 pitches");
    expect(dataset.scope).toContain("2025 Statcast pull");
    expect(dataset.scope).toContain("exact observation dates are not published");
    expect(dataset.caveat).toContain("Pooled pitch-type velocity variation is not pitcher consistency or quality");
    expect(labComparisonPolicy(dataset.rows).compatibility).toBe("unknown");
  });

  it("derives span and coverage from the matched published counts and percentiles", () => {
    const dataset = getPitchProfilesLabDataset();
    const ff = dataset.rows.find(row => row.label === "FF")!;
    const si = dataset.rows.find(row => row.label === "SI")!;
    const ch = dataset.rows.find(row => row.label === "CH")!;
    expect(ff.values).toEqual({
      p50: 94.5, p10: 91.3, p90: 97.7, pct: 31.78,
      mix_n: 220235, velocity_n: 220233,
      velocity_span: 6.4, velocity_coverage: 220233 / 220235,
    });
    expect(si.values.mix_n).toBe(107136);
    expect(si.values.velocity_n).toBe(107135);
    expect(si.values.velocity_coverage).toBe(107135 / 107136);
    expect(ch.values.mix_n).toBe(71270);
    expect(ch.values.velocity_n).toBe(71270);
    expect(ch.values.velocity_coverage).toBe(1);
    expect(displayMeasurement(ff.values.velocity_coverage, dataset.fields[7])).toBe("99.999%");
    expect(ff.note).toContain("pitch_type_distribution[0]");
    expect(ff.note).toContain("velo_percentiles_by_pitch_type[0]");
    expect(ff.note).toContain("matched by pitch_type");
    expect(ff.note).toContain("velo_percentiles_by_pitch_type[0].n / pitch_type_distribution[0].n");
    expect(ff.note).toContain("rounded independently");
  });

  it("keeps published but unmatched pitch types unavailable, without inventing a zero denominator", () => {
    const dataset = getPitchProfilesLabDataset();
    for (const label of ["UNK", "UN", "SC"]) {
      const row = dataset.rows.find(candidate => candidate.label === label)!;
      expect(row.values.velocity_n).toBeNull();
      expect(row.values.velocity_span).toBeNull();
      expect(row.values.velocity_coverage).toBeNull();
      expect(row.note).toContain("No matching published velocity row");
      expect(row.note).toContain("denominator is unavailable, not zero");
      expect(row.note).toContain(`pitch_type_distribution[${dataset.rows.indexOf(row)}]`);
      expect(row.note).not.toContain("velo_percentiles_by_pitch_type[");
    }
  });

  it("gates derived fields on valid support, without changing valid published operands", () => {
    const mix = [
      { pitch_type: "low", n: 30, pct: 0 },
      { pitch_type: "over", n: 30, pct: 3 },
      { pitch_type: "string", n: "30", pct: 4 },
      { pitch_type: "zero", n: 0, pct: 0 },
      { pitch_type: "unsafe", n: Number.MAX_SAFE_INTEGER + 1, pct: 2 },
      { pitch_type: "negative", n: -30, pct: 1 },
      { pitch_type: "fraction", n: 30.5, pct: 1 },
    ];
    const velocity = mix.map(row => ({ pitch_type: row.pitch_type, n: row.pitch_type === "low" ? 19 : row.pitch_type === "over" ? 31 : 20, p10: 0, p50: 0, p90: 0 }));
    const dataset = buildPitchProfilesLabDataset({ pitch_type_distribution: mix, velo_percentiles_by_pitch_type: velocity });
    expect(dataset.rows.map(row => row.values.velocity_coverage)).toEqual(Array(7).fill(null));
    expect(dataset.rows.map(row => row.values.velocity_span)).toEqual([null, 0, 0, 0, 0, 0, 0]);
    expect(dataset.rows.map(row => row.values.mix_n)).toEqual([30, 30, null, 0, null, null, null]);
    expect(dataset.rows[0].values.velocity_n).toBe(19);
    expect(dataset.rows[1].values.velocity_n).toBe(31);
    expect(dataset.rows[0].values.pct).toBe(0);
    expect(dataset.rows[2].note).toContain("coverage unavailable unless mix_n is a positive safe integer");
    expect(dataset.scope).toContain("total unavailable");
  });

  it("rejects invalid velocity counts and percentile order but preserves valid equal bounds", () => {
    const input = [
      { pitch_type: "equal", n: 20, p10: 80, p50: 80, p90: 80 },
      { pitch_type: "reverse", n: 20, p10: 90, p50: 85, p90: 80 },
      { pitch_type: "middle", n: 20, p10: 80, p50: 95, p90: 90 },
      { pitch_type: "negative", n: 20, p10: -1, p50: 0, p90: 1 },
      { pitch_type: "missing", n: 20, p10: 80, p50: null, p90: 90 },
      { pitch_type: "coerced", n: "20", p10: 80, p50: 85, p90: 90 },
      { pitch_type: "unsafe", n: Number.MAX_SAFE_INTEGER + 1, p10: 80, p50: 85, p90: 90 },
      { pitch_type: "overflow", n: 20, p10: 0, p50: 1e308, p90: 1e308 },
    ];
    const dataset = buildPitchProfilesLabDataset({
      n_pitches: "140",
      pitch_type_distribution: input.map(row => ({ pitch_type: row.pitch_type, n: 20, pct: 0 })),
      velo_percentiles_by_pitch_type: input,
    });
    expect(dataset.rows.map(row => row.values.velocity_span)).toEqual([0, null, null, null, null, null, null, null]);
    expect(dataset.rows.map(row => row.values.velocity_coverage)).toEqual([1, 1, 1, 1, 1, null, null, 1]);
    expect(dataset.rows[4].values.p50).toBeNull();
    expect(dataset.rows[5].values.velocity_n).toBeNull();
    expect(dataset.scope).toContain("total unavailable");
  });

  it("does not coerce missing source fields into measurements", () => {
    const dataset = buildPitchProfilesLabDataset({
      pitch_type_distribution: [{ pitch_type: "FF", n: 20 }],
      velo_percentiles_by_pitch_type: [{ pitch_type: "FF", n: 20, p10: "80", p90: 90 }],
    });
    expect(dataset.rows[0].values).toEqual({
      p50: null, p10: null, p90: 90, pct: null, mix_n: 20, velocity_n: 20,
      velocity_span: null, velocity_coverage: 1,
    });
    expect(() => buildPitchProfilesLabDataset({})).toThrow("statcast_showcase.pitch_type_distribution must be an array");
  });

  it("fails clearly when required source arrays or their rows are malformed", () => {
    expect(() => buildPitchProfilesLabDataset({
      pitch_type_distribution: [],
    })).toThrow("statcast_showcase.velo_percentiles_by_pitch_type must be an array");
    expect(() => buildPitchProfilesLabDataset({
      pitch_type_distribution: "not rows",
      velo_percentiles_by_pitch_type: [],
    })).toThrow("statcast_showcase.pitch_type_distribution must be an array");
    expect(() => buildPitchProfilesLabDataset({
      pitch_type_distribution: [null],
      velo_percentiles_by_pitch_type: [],
    })).toThrow("statcast_showcase.pitch_type_distribution[0] must be an object");
    expect(() => buildPitchProfilesLabDataset({
      pitch_type_distribution: [],
      velo_percentiles_by_pitch_type: [42],
    })).toThrow("statcast_showcase.velo_percentiles_by_pitch_type[0] must be an object");
    expect(buildPitchProfilesLabDataset({
      pitch_type_distribution: [],
      velo_percentiles_by_pitch_type: [],
    }).rows).toEqual([]);
  });
});
