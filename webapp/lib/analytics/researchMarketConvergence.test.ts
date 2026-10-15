import { describe, expect, it } from "vitest";
import { buildMarketConvergenceResearch } from "./researchMarketConvergence";
import published from "../../public/data/showcase/market_convergence.json";
import { buildLabCSV } from "../../components/analytics/lab/LabTable";

const checkpoint = (n = 40) => ({ n, mean_gap: 0.1, median_gap: 0.08, mean_entropy_market_bits: 0.8, mean_entropy_model_bits: 0.9, mean_market_prob: 0.55, mean_model_prob: 0.52 });

describe("market convergence research", () => {
  it("preserves the published source date in analysis and CSV without inferring an observation window", () => {
    const analysis = buildMarketConvergenceResearch(published)[0];
    expect(analysis.asOf).toBe(published.as_of);
    expect(analysis.scope).toContain(`Published source as of ${published.as_of}.`);
    expect(analysis.scope).toContain("This date does not identify the observation window.");
    expect(analysis.rows).toHaveLength(29);
    expect(buildLabCSV(analysis, analysis.rows)).toContain(`"${published.as_of}"`);
  });

  it.each([undefined, null, "", "unknown", "2026-02-30", 20260917])("keeps unavailable source dates explicit (%s)", as_of => {
    const analysis = buildMarketConvergenceResearch({ as_of, checkpoints: { mlb: { 2: checkpoint() } } })[0];
    expect(analysis.asOf).toBeUndefined();
    expect(analysis.scope).toContain("Source as-of date not published.");
    expect(analysis.rows[0].values.scored_rows).toBe(40);
  });

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
