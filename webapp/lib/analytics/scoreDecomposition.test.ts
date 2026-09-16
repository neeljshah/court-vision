import { describe, expect, it } from "vitest";
import { buildScoreDecomposition, formatDecompositionValue } from "./scoreDecomposition";

const fixture = { sports: { soccer_intl: { model_prob: { brier: 0.227887, reliability: 0.092837, resolution: 0.038185, uncertainty: 0.238877, reconstructed_brier: 0.293529 }, market_prob: { brier: 0.142726, reliability: 0.053423, resolution: 0.082761, uncertainty: 0.238877, reconstructed_brier: 0.209538 } } } };

describe("score decomposition data", () => {
  it("computes the signed reconstruction remainder", () => {
    expect(buildScoreDecomposition(fixture)[0].rows[0].remainder).toBeCloseTo(0.065642, 12);
  });

  it("formats published values and remainders to six decimals", () => {
    expect(formatDecompositionValue(buildScoreDecomposition(fixture)[0].rows[0].remainder)).toBe("0.065642");
  });

  it("keeps model and market populations in separate rows", () => {
    expect(buildScoreDecomposition(fixture)[0].rows.map(row => row.side)).toEqual(["model", "market"]);
  });

  it("handles a missing side without inventing a row", () => {
    expect(buildScoreDecomposition({ sports: { mlb: { model_prob: fixture.sports.soccer_intl.model_prob } } })[0].rows).toHaveLength(1);
  });
});
