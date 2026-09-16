import { describe, expect, it } from "vitest";
import { buildCalibrationReliability } from "./calibrationReliability";

const fixture = {
  n_boot: 1000, ci_pct: [2.5, 97.5], cluster_unit: "game_id", min_games_per_bin_floor: 5,
  sports: {
    mlb: { n_rows: 12, n_games: 6, low_power: false, sides: {
      model_prob: { label: "model", bins: [{ bin_lo: 0, bin_hi: 0.1, mean_p: 0.04, mean_y: 0.05, mean_y_ci: [0.01, 0.1], gap: 0.01, gap_ci: [-0.03, 0.04], n: 12, n_games: 6, low_n: true }] },
      market_prob: { label: "market", bins: [{ bin_lo: 0.1, bin_hi: 0.2, mean_p: 0.14, mean_y: 0.12, mean_y_ci: [0.08, 0.2], gap: -0.02, gap_ci: [-0.06, 0.02], n: 9, n_games: 5, low_n: false }] },
    } },
  },
};

describe("buildCalibrationReliability", () => {
  it("parses each published bin without recomputing it", () => {
    const series = buildCalibrationReliability(fixture);
    expect(series).toHaveLength(2);
    expect(series[0].bins[0]).toMatchObject({ binLo: 0, binHi: 0.1, meanP: 0.04, meanY: 0.05, n: 12, nGames: 6 });
  });

  it("preserves observed and gap confidence intervals", () => {
    const bin = buildCalibrationReliability(fixture)[0].bins[0];
    expect(bin.meanYCi).toEqual([0.01, 0.1]);
    expect(bin.gapCi).toEqual([-0.03, 0.04]);
  });

  it("retains the published low-n flag", () => {
    expect(buildCalibrationReliability(fixture)[0].bins[0].lowN).toBe(true);
  });

  it("handles a sport with a missing side", () => {
    const missing = { ...fixture, sports: { mlb: { ...fixture.sports.mlb, sides: { model_prob: fixture.sports.mlb.sides.model_prob } } } };
    expect(buildCalibrationReliability(missing)).toEqual([expect.objectContaining({ sport: "mlb", side: "model" })]);
  });

  it("normalizes null confidence-interval values", () => {
    const changed: unknown = { ...fixture, sports: { mlb: { ...fixture.sports.mlb, sides: { ...fixture.sports.mlb.sides, model_prob: { ...fixture.sports.mlb.sides.model_prob, bins: [{ ...fixture.sports.mlb.sides.model_prob.bins[0], mean_y_ci: [null, Number.NaN] }] } } } } };
    expect(buildCalibrationReliability(changed)[0].bins[0].meanYCi).toEqual([null, null]);
  });
});
