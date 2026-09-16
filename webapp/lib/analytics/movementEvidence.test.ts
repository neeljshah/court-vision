import absorptionSource from "@/public/data/showcase/micro_absorption.json";
import overreactionSource from "@/public/data/showcase/market_overreaction.json";
import { describe, expect, it } from "vitest";
import { buildMovementEvidence } from "./movementEvidence";

describe("movement evidence", () => {
  const evidence = buildMovementEvidence(overreactionSource, absorptionSource);

  it("keeps all ten overreaction buckets with both operands and their signs", () => {
    expect(evidence.overreaction.rows).toHaveLength(10);
    for (const [sport, buckets] of Object.entries(overreactionSource.buckets)) {
      for (const [bucket, value] of Object.entries(buckets)) {
        const row = evidence.overreaction.rows.find(candidate => candidate.sport === (sport === "soccer_intl" ? "International soccer" : sport.toUpperCase()) && candidate.bucket === bucket);
        expect(row).toBeDefined();
        expect(row).toMatchObject({ movedToPrice: value.moved_to_price, outcomeRate: value.outcome_rate, statedDifference: value.moved_to_minus_outcome });
        expect(row?.derivedDifference).toBe(Number((value.moved_to_price - value.outcome_rate).toFixed(6)));
        expect(Math.sign(row?.derivedDifference || 0)).toBe(Math.sign(value.moved_to_minus_outcome));
      }
    }
  });

  it("preserves sport-specific observation windows and marks unavailable coverage", () => {
    const nba = evidence.absorption.rows.find(row => row.sport === "NBA");
    const internationalSoccer = evidence.absorption.rows.find(row => row.sport === "International soccer");
    const kbo = evidence.absorption.rows.find(row => row.sport === "KBO");
    expect(nba?.observationWindow).toMatchObject({ start: "2026-06-18", end: "2026-07-17", days: 30 });
    expect(internationalSoccer?.observationWindow).toMatchObject({ start: "2026-06-19", end: "2026-07-17", days: 29 });
    expect(kbo).toMatchObject({ availability: "unavailable", intervalMinutes: { median: null, p90: null, mean: null }, meanMovementPerPair: null });
    expect(evidence.absorption.independentGameCountsUnavailable).toBe(true);
  });
});
