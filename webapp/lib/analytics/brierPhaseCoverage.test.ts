import { describe, expect, it } from "vitest";
import published from "../../public/data/showcase/brier_skill_scores.json";
import { buildBrierPhaseCoverage } from "./brierPhaseCoverage";

const mlb = (all: unknown = 6, early: unknown = 1, mid: unknown = 2, late: unknown = 3) => ({
  sports: { mlb: { grains: {
    all: { n: all },
    "early(inn1-3)": { n: early },
    "mid(inn4-6)": { n: mid },
    "late(inn7+)": { n: late },
  } } },
});

describe("buildBrierPhaseCoverage", () => {
  it("describes the published scored-row phase coverage", () => {
    expect(buildBrierPhaseCoverage(published)).toEqual([
      expect.objectContaining({ sport: "mlb", label: "MLB", total: 27351, classified: 26683, outside: 668, fraction: 26683 / 27351, reason: null }),
      expect.objectContaining({ sport: "soccer_intl", label: "International soccer", total: 4265, classified: 3383, outside: 882, fraction: 3383 / 4265, reason: null }),
    ]);
  });

  it("uses exact support operands in source paths", () => {
    expect(buildBrierPhaseCoverage(mlb())[0].sourcePaths).toEqual([
      "sports.mlb.grains.all.n",
      "sports.mlb.grains.early(inn1-3).n",
      "sports.mlb.grains.mid(inn4-6).n",
      "sports.mlb.grains.late(inn7+).n",
    ]);
  });

  it("does not silently replace a missing phase with zero", () => {
    const source = mlb();
    delete (source.sports.mlb.grains as Record<string, unknown>)["mid(inn4-6)"];
    expect(buildBrierPhaseCoverage(source)[0]).toMatchObject({ total: 6, classified: null, outside: null, fraction: null, reason: expect.stringContaining("missing or invalid") });
  });

  it.each([NaN, Infinity, -1, 1.5])("rejects invalid phase support %s", value => {
    expect(buildBrierPhaseCoverage(mlb(6, value))[0]).toMatchObject({ total: 6, classified: null, outside: null, fraction: null });
  });

  it("rejects an invalid total while preserving no derived counts", () => {
    expect(buildBrierPhaseCoverage(mlb(-1))[0]).toMatchObject({ total: null, classified: null, outside: null, fraction: null, reason: expect.stringContaining("all-row") });
  });

  it("rejects a phase sum above the valid total", () => {
    expect(buildBrierPhaseCoverage(mlb(5))[0]).toMatchObject({ total: 5, classified: null, outside: null, fraction: null, reason: expect.stringContaining("valid subset") });
  });

  it("keeps zero support explicit and leaves its fraction undefined", () => {
    expect(buildBrierPhaseCoverage(mlb(0, 0, 0, 0))[0]).toMatchObject({ total: 0, classified: 0, outside: 0, fraction: null, reason: null });
  });

  it("rejects extra grains because the known partition is no longer complete", () => {
    const source = mlb();
    (source.sports.mlb.grains as Record<string, unknown>).postponed = { n: 1 };
    const result = buildBrierPhaseCoverage(source)[0];
    expect(result).toMatchObject({ total: 6, classified: null, outside: null, fraction: null, reason: expect.stringContaining("Unexpected phase") });
    expect(result.sourcePaths).toContain("sports.mlb.grains.postponed.n");
  });

  it("reports malformed and unsupported sport structures as unavailable", () => {
    expect(buildBrierPhaseCoverage({ sports: null })).toEqual([]);
    expect(buildBrierPhaseCoverage({ sports: { mlb: [] } })[0]).toMatchObject({ sport: "mlb", total: null, classified: null, reason: expect.any(String) });
    expect(buildBrierPhaseCoverage({ sports: { tennis: { grains: { all: { n: 12 } } } } })[0]).toMatchObject({ sport: "tennis", total: 12, classified: null, reason: expect.stringContaining("No published phase partition") });
    for (const sport of ["constructor", "toString"]) {
      const result = buildBrierPhaseCoverage({ sports: { [sport]: { grains: { all: { n: 12 } } } } })[0];
      expect(result).toMatchObject({ sport, total: 12, classified: null, reason: expect.stringContaining("No published phase partition") });
    }
  });
});
