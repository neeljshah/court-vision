import { describe, expect, it } from "vitest";
import { getMultisportDepthResearch } from "./researchMultisportDepth";

const analyses = getMultisportDepthResearch();

describe("getMultisportDepthResearch", () => {
  it("adds four public-snapshot analyses with inspectable formulas", () => {
    expect(analyses).toHaveLength(4);
    expect(analyses.map(analysis => analysis.id)).toEqual(["mlb-velocity-band-concentration", "mlb-shrinkage-displacement", "soccer-minute-calibration-support", "tennis-surface-prior-brier-delta"]);
    analyses.forEach(analysis => expect(analysis.formula).toBeTruthy());
  });

  it("keeps support, shrinkage movement, and rejected surface deltas explicit", () => {
    const soccer = analyses.find(analysis => analysis.id === "soccer-minute-calibration-support")!;
    expect(soccer.rows.reduce((sum, row) => sum + (row.values.support_share || 0), 0)).toBeCloseTo(1, 5);
    const shrinkage = analyses.find(analysis => analysis.id === "mlb-shrinkage-displacement")!;
    expect(shrinkage.rows.some(row => (row.values.absolute_regression || 0) > 0)).toBe(true);
    expect(new Set(shrinkage.rows.map(row => row.group))).toEqual(new Set([
      "Catcher out-of-zone strike rate (NOT a framing/called-strike rate; descriptive)",
      "Umpire out-of-zone strike rate (NOT a framing/called-strike rate; descriptive)",
      "On-base rate vs LHP (descriptive)",
    ]));
    expect(shrinkage.scope).toContain("2022-2023");
    shrinkage.rows.forEach(row => expect(row.values.regression).toBe(Number((row.values.shrunk_rate! - row.values.raw_rate!).toFixed(6))));
    expect(shrinkage.rows.find(row => row.label === "Drew Millas")?.values.regression).toBe(0.0408);
    expect(shrinkage.rows.some(row => (row.values.regression || 0) < 0)).toBe(true);
    const tennis = analyses.find(analysis => analysis.id === "tennis-surface-prior-brier-delta")!;
    expect(tennis.status).toBe("Descriptive reject");
    expect(tennis.rows.every(row => (row.values.delta || 0) > 0)).toBe(true);
    tennis.rows.forEach(row => expect(row.values.higher_error_folds).toBe(row.values.n_folds));
  });
});
