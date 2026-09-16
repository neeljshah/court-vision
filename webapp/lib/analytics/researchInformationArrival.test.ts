import { describe, expect, it } from "vitest";
import { buildInformationArrivalResearch } from "./researchInformationArrival";

const checkpoint = (n = 40) => ({ n, model_brier: 0.23, market_brier: 0.2, naive_brier: 0.24, market_minus_model_brier: -0.03 });

describe("information arrival research", () => {
  it("builds checkpoint measurements and field paths", () => {
    const analysis = buildInformationArrivalResearch({ checkpoints: { mlb: { 2: checkpoint() } } })[0];
    expect(analysis).toMatchObject({ id: "information-arrival-brier-by-checkpoint", source: "info_arrival_curve" });
    expect(analysis.rows[0].values).toMatchObject({ model_brier: 0.23, market_minus_model_brier: -0.03, scored_rows: 40 });
    expect(analysis.rows[0].sourcePaths).toContain("checkpoints.mlb.2.model_brier");
  });

  it("orders sport rows and flags small support without dropping it", () => {
    const rows = buildInformationArrivalResearch({ checkpoints: { soccer_intl: { 5: checkpoint(18) }, mlb: { 2: checkpoint() } } })[0].rows;
    expect(rows.map(item => item.label)).toEqual(["International soccer | 5'", "MLB | Inning 2"]);
    expect(rows[0].note).toContain("Small support");
  });

  it("returns no rows for missing or malformed checkpoints", () => {
    expect(buildInformationArrivalResearch({ checkpoints: { mlb: { 1: { ...checkpoint(), naive_brier: -1 } } } })[0].rows).toEqual([]);
    expect(buildInformationArrivalResearch({})[0].rows).toEqual([]);
  });
});
