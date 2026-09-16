import { describe, expect, it } from "vitest";
import {
  buildMlbBatterContactResearch,
  getMlbBatterContactResearch,
  type MlbBatterContactEntry,
} from "./researchMlbBatterContact";

const FLOOR = "pitches_faced_2025>=300 (yields public subset)";
const entry = (entity: unknown, key_numbers: Record<string, unknown>, floors: unknown = FLOOR, batterId = 1): MlbBatterContactEntry => ({
  entity, key_numbers: { batter_id: batterId, ...key_numbers }, floors, as_of: "2025-09-28",
});

describe("MLB batter recorded exit-velocity research", () => {
  it("covers the public atlas and preserves the published operands and support", () => {
    const analysis = getMlbBatterContactResearch()[0];
    expect(analysis.rows).toHaveLength(485);
    const judge = analysis.rows.find(row => row.label === "Aaron Judge")!;
    expect(judge.values).toMatchObject({ exit_velo_p90: 109.5, avg_exit_velo: 87.6, recorded_exit_velocities: 698, pitches_faced: 2715 });
    expect(judge.values.p90_minus_mean_exit_velo).toBeCloseTo(21.9, 10);
    expect(judge.id).toBe("mlb-contact-592450");
    expect(judge.note).toContain("Source batter_id 592450.");
    const arraez = analysis.rows.find(row => row.label === "Luis Arraez")!;
    expect(arraez.values).toMatchObject({ exit_velo_p90: 95.4, avg_exit_velo: 81.2, recorded_exit_velocities: 1072, pitches_faced: 2393 });
    expect(arraez.values.p90_minus_mean_exit_velo).toBeCloseTo(14.2, 10);
  });

  it("states the source semantics and keeps input and generation dates distinct", () => {
    const analysis = getMlbBatterContactResearch()[0];
    expect(analysis.scope).toContain("latest global input date 2025-09-28");
    expect(analysis.scope).toContain("public artifact generated 2026-07-23");
    expect(analysis.asOf).toBeUndefined();
    expect(analysis.caveat).toContain("does not load event, type, or description fields");
    expect(analysis.caveat).toContain("does not establish balls in play, official batted-ball events, or whether fouls are included");
    expect(analysis.caveat).toContain("no earliest-date, completeness, or game-type audit");
    expect(analysis.formula).toContain("same non-missing launch_speed series");
    expect(analysis.fields.map(field => [field.key, field.unit, field.digits])).toEqual([
      ["p90_minus_mean_exit_velo", "mph", 1], ["exit_velo_p90", "mph", 1], ["avg_exit_velo", "mph", 1],
      ["recorded_exit_velocities", "number", 0], ["pitches_faced", "number", 0],
    ]);
  });

  it("fails closed on malformed values, support, identity, and eligibility", () => {
    const valid = entry("Valid", { avg_exit_velo: 0, exit_velo_p90: 0, n_batted_balls: 1, pitches_faced: 300 });
    const invalid = [
      entry("", { avg_exit_velo: 80, exit_velo_p90: 90, n_batted_balls: 1, pitches_faced: 300 }, FLOOR, 2),
      entry("Missing", { avg_exit_velo: null, exit_velo_p90: 90, n_batted_balls: 1, pitches_faced: 300 }, FLOOR, 3),
      entry("Infinite", { avg_exit_velo: 80, exit_velo_p90: Infinity, n_batted_balls: 1, pitches_faced: 300 }, FLOOR, 4),
      entry("Negative", { avg_exit_velo: -1, exit_velo_p90: 90, n_batted_balls: 1, pitches_faced: 300 }, FLOOR, 5),
      entry("No support", { avg_exit_velo: 80, exit_velo_p90: 90, n_batted_balls: 0, pitches_faced: 300 }, FLOOR, 6),
      entry("Fractional support", { avg_exit_velo: 80, exit_velo_p90: 90, n_batted_balls: 1.5, pitches_faced: 300 }, FLOOR, 7),
      entry("Support exceeds pitches", { avg_exit_velo: 80, exit_velo_p90: 90, n_batted_balls: 301, pitches_faced: 300 }, FLOOR, 8),
      entry("Below floor", { avg_exit_velo: 80, exit_velo_p90: 90, n_batted_balls: 1, pitches_faced: 299 }, FLOOR, 9),
      entry("Wrong floor", { avg_exit_velo: 80, exit_velo_p90: 90, n_batted_balls: 1, pitches_faced: 300 }, "pitches_faced_2025>=30", 10),
      entry("Extra digit", { avg_exit_velo: 80, exit_velo_p90: 90, n_batted_balls: 1, pitches_faced: 300 }, "pitches_faced_2025>=3000", 11),
      entry("Decimal floor", { avg_exit_velo: 80, exit_velo_p90: 90, n_batted_balls: 1, pitches_faced: 300 }, "pitches_faced_2025>=300.5", 12),
      entry("Missing floor", { avg_exit_velo: 80, exit_velo_p90: 90, n_batted_balls: 1, pitches_faced: 300 }, null, 13),
      entry("Missing ID", { batter_id: undefined, avg_exit_velo: 80, exit_velo_p90: 90, n_batted_balls: 1, pitches_faced: 300 }, FLOOR, 14),
    ];
    const rows = buildMlbBatterContactResearch({ entries: [valid, ...invalid] })[0].rows;
    expect(rows).toHaveLength(1);
    expect(rows[0].values).toMatchObject({ p90_minus_mean_exit_velo: 0, avg_exit_velo: 0, exit_velo_p90: 0 });
    expect(rows[0].id).toBe("mlb-contact-1");
  });

  it("uses stable source IDs and rejects every row with a duplicate ID", () => {
    const values = { avg_exit_velo: 80, exit_velo_p90: 90, n_batted_balls: 25, pitches_faced: 300 };
    const unique = entry("Unique", values, FLOOR, 7);
    const duplicateA = entry("Duplicate A", values, FLOOR, 8);
    const duplicateB = entry("Duplicate B", values, FLOOR, 8);
    const rows = buildMlbBatterContactResearch({ entries: [duplicateB, unique, duplicateA] })[0].rows;
    expect(rows.map(row => [row.id, row.label])).toEqual([["mlb-contact-7", "Unique"]]);
    expect(rows[0].note).toContain("Source batter_id 7.");
  });

  it("retains a valid negative signed difference without adding unsupported claims", () => {
    const analysis = buildMlbBatterContactResearch({
      generated_at: "2026-01-02T00:00:00Z", n_entries: 1,
      entries: [entry("Fixture", { avg_exit_velo: 90, exit_velo_p90: 80, n_batted_balls: 25, pitches_faced: 300 })],
    })[0];
    expect(analysis.rows[0].values.p90_minus_mean_exit_velo).toBe(-10);
    expect(analysis.rows[0].note).toContain("25 rows have recorded launch_speed among 300 pitches faced");
    expect(`${analysis.title} ${analysis.description} ${analysis.interpretation}`.toLowerCase()).not.toMatch(/consisten|barrel|predict|novel/);
  });
});
