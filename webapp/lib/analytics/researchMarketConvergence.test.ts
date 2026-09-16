import { describe, expect, it } from "vitest";
import { buildMarketConvergenceResearch } from "./researchMarketConvergence";

const checkpoint = (n = 40) => ({ n, mean_gap: 0.1, median_gap: 0.08, mean_entropy_market_bits: 0.8, mean_entropy_model_bits: 0.9, mean_market_prob: 0.55, mean_model_prob: 0.52 });

describe("market convergence research", () => {
  it("builds each published convergence measurement with source paths", () => {
    const analysis = buildMarketConvergenceResearch({ checkpoints: { mlb: { 2: checkpoint() } } })[0];
    expect(analysis).toMatchObject({ id: "market-convergence-by-checkpoint", source: "market_convergence" });
    expect(analysis.rows[0].values).toMatchObject({ mean_gap: 0.1, market_entropy_bits: 0.8, scored_rows: 40 });
    expect(analysis.rows[0].sourcePaths).toContain("checkpoints.mlb.2.mean_gap");
  });

  it("orders sport rows and checkpoint labels deterministically", () => {
    const rows = buildMarketConvergenceResearch({ checkpoints: { soccer_intl: { 15: checkpoint() }, mlb: { 2: checkpoint(), 10: checkpoint() } } })[0].rows;
    expect(rows.map(item => item.label)).toEqual(["International soccer | 15'", "MLB | Inning 2", "MLB | Inning 10"]);
  });

  it("returns no rows for missing or malformed checkpoints", () => {
    expect(buildMarketConvergenceResearch({ checkpoints: { mlb: { 1: { ...checkpoint(), mean_gap: -1 } } } })[0].rows).toEqual([]);
    expect(buildMarketConvergenceResearch({})[0].rows).toEqual([]);
  });
});
