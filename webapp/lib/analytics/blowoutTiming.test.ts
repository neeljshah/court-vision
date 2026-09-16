import { describe, expect, it } from "vitest";
import { buildBlowoutTiming, incidenceFraction } from "./blowoutTiming";
import { loadBlowoutTiming } from "./blowoutTiming.server";

describe("blowout timing data", () => {
  it("parses all seven published thresholds", () => {
    const sports = loadBlowoutTiming();
    expect(sports.flatMap(sport => sport.thresholds)).toHaveLength(7);
    expect(sports.map(sport => sport.thresholds.length)).toEqual([4, 3]);
  });

  it("keeps the two masked soccer thresholds and their published status", () => {
    const soccer = loadBlowoutTiming().find(sport => sport.sport === "soccer_intl");
    expect(soccer?.thresholds.filter(row => row.masked).map(row => row.threshold)).toEqual([2, 3]);
    expect(soccer?.thresholds.filter(row => row.masked).every(row => row.maskReason?.includes("10 decided games"))).toBe(true);
  });

  it("preserves the published clock field and margin unit for each sport", () => {
    const sports = loadBlowoutTiming();
    expect(sports.find(sport => sport.sport === "mlb")).toMatchObject({ unit: "runs", clockField: "inning" });
    expect(sports.find(sport => sport.sport === "soccer_intl")).toMatchObject({ unit: "goals", clockField: "minute" });
  });

  it("derives incidence from decided games and total games on a fixture", () => {
    const parsed = buildBlowoutTiming({ sports: { fixture: { unit: "points", clock_field: "minute", thresholds: [{ threshold: 8, n_games_total: 3, n_games_decided: 1, decided_frac_of_games: 0.9 }] } } });
    expect(parsed[0].thresholds[0].incidence).toBe(0.333333);
    expect(parsed[0].thresholds[0].publishedIncidence).toBe(0.9);
    expect(incidenceFraction(1, 3)).toBe(0.333333);
  });
});
