import { describe, expect, it } from "vitest";
import source from "@/public/data/showcase/mlb_count_leverage.json";
import { buildExactCountContext } from "./exactCountContext";

const validRow = {
  balls: 0, strikes: 0, leverage_class: "even", n: 0,
  top_pitch_type: null, top_pitch_pct: 0,
  strike_rate_type_S: 0, in_zone_rate: 0,
};

describe("exact count context", () => {
  it("preserves published zero and null while nulling missing or out-of-range metrics", () => {
    const data = buildExactCountContext({
      status: "ok", as_of: null, by_exact_count: [
        validRow,
        { balls: 0, strikes: 1, leverage_class: "ahead", n: -1,
          top_pitch_pct: 101, strike_rate_type_S: 1.01, in_zone_rate: Number.NaN },
      ],
    });
    expect(data.rows[0]).toMatchObject({
      n: 0, topPitchType: null, topPitchPct: 0, strikeRate: 0, inZoneRate: 0,
    });
    expect(data.rows[1]).toMatchObject({
      n: null, topPitchType: null, topPitchPct: null, strikeRate: null, inZoneRate: null,
    });
    expect(data.asOf).toBeNull();
  });

  it("fails closed for unavailable sources, invalid counts, and duplicate count rows", () => {
    expect(buildExactCountContext({ status: "not_ok", by_exact_count: [validRow] }).rows).toEqual([]);
    expect(buildExactCountContext({ status: "ok", by_exact_count: [
      { ...validRow, balls: 4 },
    ] }).rows).toEqual([]);
    expect(buildExactCountContext({ status: "ok", by_exact_count: [
      validRow, { ...validRow, n: 10 },
    ] }).rows).toEqual([]);
  });

  it("parses the complete published exact-count grid without invented denominators", () => {
    const data = buildExactCountContext(source);
    expect(data.rows).toHaveLength(12);
    expect(data.rows.reduce((total, row) => total + (row.n ?? 0), 0)).toBe(693037);
    expect(data.rows.find(row => row.id === "0-0")).toMatchObject({
      leverageClass: "even", n: 178407, topPitchType: "FF", topPitchPct: 32.77,
      strikeRate: 0.5038, inZoneRate: 0.5503,
    });
    expect(data.rows.find(row => row.id === "3-0")).toMatchObject({
      leverageClass: "behind", n: 7457, topPitchPct: 65.12,
      strikeRate: 0.5723, inZoneRate: 0.6293,
    });
    expect(data.rows.find(row => row.id === "0-2")).toMatchObject({
      leverageClass: "ahead", n: 46656, topPitchPct: 31.77,
      strikeRate: 0.3603, inZoneRate: 0.3241,
    });
    expect(Object.keys(data.rows[0])).not.toContain("nType");
    expect(Object.keys(data.rows[0])).not.toContain("nZone");
  });

  it("rejects classes that contradict the published pre-pitch count definition", () => {
    for (const leverage_class of ["ahead", "unknown"]) {
      expect(buildExactCountContext({ status: "ok", by_exact_count: [
        validRow, { ...validRow, balls: 3, leverage_class },
      ] }).rows).toEqual([]);
    }
  });
});
