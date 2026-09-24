import { describe, expect, it } from "vitest";
import { buildMlbPlatoonSupportResearch, getMlbPlatoonSupportResearch } from "./researchMlbPlatoonSupport";

const entry = (name: string, left: unknown, right: unknown, overrides: Record<string, unknown> = {}) => ({
  name, rate_vs_l: 0.4, rate_vs_r: 0.3, platoon_delta: 0.1, pa_vs_l: left, pa_vs_r: right, ...overrides,
});
const source = (top: unknown[]) => ({
  observation_window: { seasons: "2022_2023", corpus_id: "statcast_fuller_v1" },
  platoon_splits: { floor: "pa_vs_l>=50 and pa_vs_r>=50", n_qualified: 394, top },
});

describe("MLB platoon support balance", () => {
  it("preserves published zero counts without calculating a below-floor support share", () => {
    const analysis = buildMlbPlatoonSupportResearch(source([entry("Zero support", 0, 0)]));
    expect(analysis.rows[0].values).toMatchObject({ pa_vs_l: 0, pa_vs_r: 0, smaller_side_support_share: null });
  });

  it("uses the published selection, counts, gap, and source indices without rebuilding rounded rates", () => {
    const analysis = getMlbPlatoonSupportResearch()[0];
    expect(analysis.id).toBe("mlb-platoon-support-balance");
    expect(analysis.rows).toHaveLength(15);
    expect(analysis.scope).toContain("15 published upper selections of 394 floor-qualified batters");
    expect(analysis.scope).toContain("fixed 2022-2023 sampled Statcast corpus");
    expect(analysis.scope).toContain("source corpus ID statcast_fuller_v1");
    expect(analysis.scope).toContain("source as-of timestamp 2026-07-05T02:39:36.769430+00:00");
    expect(analysis.scope).toContain("public artifact generated 2026-07-24T21:46:01.294251+00:00");
    expect(analysis.caveat).toContain("timestamps are not individual observation dates");
    expect(analysis.populationDefinition?.status).toBe("unpublished");
    expect(analysis.asOf).toBeUndefined();
    const garver = analysis.rows[0];
    expect(garver.label).toBe("Mitch Garver");
    expect(garver.values).toMatchObject({
      rate_vs_l: 0.453, rate_vs_r: 0.3, platoon_delta: 0.152, pa_vs_l: 148, pa_vs_r: 413,
    });
    expect(garver.values.smaller_side_support_share).toBeCloseTo(148 / 561, 12);
    expect(garver.sourcePaths).toEqual([
      "platoon_splits.top[0].name", "platoon_splits.top[0].rate_vs_l", "platoon_splits.top[0].rate_vs_r",
      "platoon_splits.top[0].platoon_delta", "platoon_splits.top[0].pa_vs_l", "platoon_splits.top[0].pa_vs_r",
    ]);
    const haggerty = analysis.rows.find(row => row.label === "Sam Haggerty")!;
    expect(haggerty.values).toMatchObject({ platoon_delta: 0.108, pa_vs_l: 154, pa_vs_r: 156 });
    expect(haggerty.values.smaller_side_support_share).toBeCloseTo(154 / 310, 12);
    expect(analysis.fields.map(field => [field.key, field.unit])).toEqual([
      ["smaller_side_support_share", "percent"], ["platoon_delta", "pp"],
      ["rate_vs_l", "percent"], ["rate_vs_r", "percent"], ["pa_vs_l", "number"], ["pa_vs_r", "number"],
    ]);
  });

  it("preserves named sparse rows and valid operands while leaving missing or below-floor support unavailable", () => {
    const analysis = buildMlbPlatoonSupportResearch(source([
      entry("Missing left", null, 100, { rate_vs_l: null, platoon_delta: -0.1 }),
      entry("Below floor", 49, 100, { rate_vs_r: 2 }),
      entry("Valid", 50, 50, { rate_vs_l: 0, rate_vs_r: 0, platoon_delta: 0 }),
      entry("Invalid count", 75.5, 100, { platoon_delta: Infinity }),
      entry("Repeated", 60, 120),
      entry("Repeated", 80, 80),
    ]));
    expect(analysis.rows).toHaveLength(6);
    expect(analysis.rows.map(row => row.id)).toEqual([
      "mlb-platoon-selection-0", "mlb-platoon-selection-1", "mlb-platoon-selection-2",
      "mlb-platoon-selection-3", "mlb-platoon-selection-4", "mlb-platoon-selection-5",
    ]);
    expect(analysis.rows[0].values).toMatchObject({ pa_vs_l: null, pa_vs_r: 100, rate_vs_l: null, platoon_delta: -0.1, smaller_side_support_share: null });
    expect(analysis.rows[1].values).toMatchObject({ pa_vs_l: 49, pa_vs_r: 100, rate_vs_r: null, smaller_side_support_share: null });
    expect(analysis.rows[2].values).toMatchObject({ rate_vs_l: 0, rate_vs_r: 0, platoon_delta: 0, smaller_side_support_share: 0.5 });
    expect(analysis.rows[3].values).toMatchObject({ pa_vs_l: null, pa_vs_r: 100, platoon_delta: null, smaller_side_support_share: null });
    expect(analysis.rows[4].label).toBe("Repeated");
    expect(analysis.rows[5].label).toBe("Repeated");
    expect(analysis.rows[5].sourcePaths?.[0]).toBe("platoon_splits.top[5].name");
    expect(analysis.rows[0].note).toContain("Support share unavailable");
  });

  it("does not turn an unknown observation window or source floor into a verified one", () => {
    const analysis = buildMlbPlatoonSupportResearch({ platoon_splits: { top: [entry("One", 50, 100)] } });
    expect(analysis.scope).toContain("observation window not verified");
    expect(analysis.scope).toContain("published floor not verified");
    expect(analysis.scope).not.toContain("394");
    expect(analysis.caveat).toContain("observation window or corpus ID is missing or unverified");
    expect(analysis.scope).toContain("source corpus ID not published");
    expect(analysis.scope).toContain("source as-of timestamp not published or invalid");
    expect(analysis.scope).toContain("public artifact generated not published or invalid");
    expect(analysis.rows[0].values.smaller_side_support_share).toBeNull();
  });

  it("requires the matching corpus before stating the sample duration and rejects an unsafe count sum", () => {
    const analysis = buildMlbPlatoonSupportResearch({
      ...source([entry("Huge counts", Number.MAX_SAFE_INTEGER - 50, 100)]),
      observation_window: { seasons: "2022_2023", corpus_id: "other", as_of: "invalid" },
      generated_at: "invalid",
    });
    expect(analysis.scope).toContain("source corpus ID other");
    expect(analysis.scope).toContain("observation window not verified");
    expect(analysis.caveat).not.toContain("18-day samples");
    expect(analysis.rows[0].values).toMatchObject({
      pa_vs_l: Number.MAX_SAFE_INTEGER - 50, pa_vs_r: 100, smaller_side_support_share: null,
    });
    expect(analysis.rows[0].note).toContain("sum must be a safe integer");
  });
});
