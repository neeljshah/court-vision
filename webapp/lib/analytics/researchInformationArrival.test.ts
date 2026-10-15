import { describe, expect, it } from "vitest";
import { buildInformationArrivalResearch } from "./researchInformationArrival";
import published from "../../public/data/showcase/info_arrival_curve.json";
import { buildLabCSV } from "../../components/analytics/lab/LabTable";

const checkpoint = (n = 40) => ({ n, model_brier: 0.23, market_brier: 0.2, naive_brier: 0.24, market_minus_model_brier: -0.03 });

describe("information arrival research", () => {
  it("preserves the published source date in analysis and CSV without inferring an observation window", () => {
    const analysis = buildInformationArrivalResearch(published)[0];
    expect(analysis.asOf).toBe(published.as_of);
    expect(analysis.scope).toContain(`Published source as of ${published.as_of}.`);
    expect(analysis.scope).toContain("This date does not identify the observation window.");
    expect(analysis.rows).toHaveLength(30);
    expect(buildLabCSV(analysis, analysis.rows)).toContain(`"${published.as_of}"`);
  });

  it.each([undefined, null, "", "unknown", "2026-02-30", 20260916])("keeps unavailable source dates explicit (%s)", as_of => {
    const analysis = buildInformationArrivalResearch({ as_of, checkpoints: { mlb: { 2: checkpoint() } } })[0];
    expect(analysis.asOf).toBeUndefined();
    expect(analysis.scope).toContain("Source as-of date not published.");
    expect(analysis.rows[0].values.scored_rows).toBe(40);
  });

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
