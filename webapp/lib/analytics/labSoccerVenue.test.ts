import { describe, expect, it } from "vitest";
import { buildSoccerVenueLabDataset, getSoccerVenueLabDataset } from "./labSoccerVenue";

describe("soccer venue lab dataset", () => {
  it("retains the two published aggregate eras and derives shares from their counts", () => {
    const dataset = getSoccerVenueLabDataset();
    expect(dataset.id).toBe("soccer-home-advantage");
    expect(dataset.fields.map(field => field.key)).toEqual([
      "true_home_goal_diff", "neutral_goal_diff", "effect_goal_diff",
      "n_true_home", "n_neutral", "neutral_match_share",
    ]);
    expect(dataset.scope).toContain("49,425 played international matches");
    expect(dataset.scope).toContain("1872-11-30 to 2026-06-16");
    expect(dataset.rows.map(row => row.label)).toEqual(["pre-2000", "2000+"]);
    const [earlier, later] = dataset.rows;
    expect(earlier.values).toEqual({
      true_home_goal_diff: 0.6743, neutral_goal_diff: 0.4556,
      effect_goal_diff: 0.2187, n_true_home: 18235, n_neutral: 5827,
      neutral_match_share: 5827 / (18235 + 5827),
    });
    expect(later.values).toEqual({
      true_home_goal_diff: 0.6745, neutral_goal_diff: 0.176,
      effect_goal_diff: 0.4985, n_true_home: 18115, n_neutral: 7248,
      neutral_match_share: 7248 / (18115 + 7248),
    });
    expect(earlier.definition?.observationWindow).toBe("pre-2000");
    expect(later.definition?.observationWindow).toBe("2000+");
    expect(earlier.note).toContain("by_era[0].n_neutral");
    expect(later.note).toContain("by_era[1].n_true_home");
    expect(later.note).toContain("not a match-level distribution");
  });

  it("keeps valid zeros and missing fields independently, without reconstructing gaps", () => {
    const dataset = buildSoccerVenueLabDataset({
      by_era: [
        { era: "pre-2000", n_true_home: 2, n_neutral: 0, true_home_goal_diff: 0, neutral_goal_diff: null, effect_goal_diff: -0.3 },
        { era: "2000+", n_true_home: 0, n_neutral: 0, true_home_goal_diff: 1, neutral_goal_diff: 0, effect_goal_diff: null },
        { era: "other", n_true_home: 3, n_neutral: undefined, true_home_goal_diff: 0.1, neutral_goal_diff: 0.2 },
      ],
    });
    expect(dataset.rows.map(row => row.label)).toEqual(["pre-2000", "2000+", "other"]);
    expect(dataset.rows[0].values.neutral_match_share).toBe(0);
    expect(dataset.rows[0].values.true_home_goal_diff).toBe(0);
    expect(dataset.rows[0].values.neutral_goal_diff).toBeNull();
    expect(dataset.rows[0].values.effect_goal_diff).toBe(-0.3);
    expect(dataset.rows[1].values.neutral_match_share).toBeNull();
    expect(dataset.rows[1].values.neutral_goal_diff).toBe(0);
    expect(dataset.rows[1].values.effect_goal_diff).toBeNull();
    expect(dataset.rows[2].values.n_neutral).toBeNull();
    expect(dataset.rows[2].values.neutral_match_share).toBeNull();
    expect(dataset.rows[2].note).toContain("era rule not defined by producer");
    expect(dataset.scope).toContain("Overall observation window unavailable");
  });

  it("rejects coerced or unsafe support counts and unsafe summed denominators", () => {
    const dataset = buildSoccerVenueLabDataset({
      by_era: [
        { era: "a", n_true_home: "2", n_neutral: 1 },
        { era: "b", n_true_home: -1, n_neutral: 1 },
        { era: "c", n_true_home: 1.5, n_neutral: 1 },
        { era: "d", n_true_home: Number.MAX_SAFE_INTEGER, n_neutral: 1 },
        { era: "e", n_true_home: 1, n_neutral: 2 },
        { n_true_home: 1, n_neutral: 1 },
      ],
    });
    expect(dataset.rows).toHaveLength(5);
    expect(dataset.rows.slice(0, 3).map(row => row.values.n_true_home)).toEqual([null, null, null]);
    expect(dataset.rows.slice(0, 4).map(row => row.values.neutral_match_share)).toEqual([null, null, null, null]);
    expect(dataset.rows[4].values.neutral_match_share).toBe(2 / 3);
  });
});
