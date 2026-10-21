import { describe, expect, it } from "vitest";
import { groupResults, rankHits, STARTING_POINTS, titleTier, type PaletteRecord } from "./paletteRank";

const rec = (id: string, title: string, type: PaletteRecord["type"]): PaletteRecord => ({ id, title, subtitle: type, href: `/${id}`, type, keywords: [] });
const records = new Map<string, PaletteRecord>([
  ["p1", rec("p1", "Calibration reliability", "page")],
  ["m1", rec("m1", "Calibration Stability", "module")],
  ["m2", rec("m2", "Minute-Bucket Calibration Support", "module")],
  ["f1", rec("f1", "Reliability diagrams", "finding")],
]);
const lookup = (id: string) => records.get(id);

describe("paletteRank", () => {
  it("tiers titles: exact, prefix, phrase, other", () => {
    expect(titleTier("calibration stability", "Calibration Stability")).toBe(0);
    expect(titleTier("Cross sport comparability", "Cross-sport comparability")).toBe(0);
    expect(titleTier("calibration", "Calibration reliability")).toBe(1);
    expect(titleTier("calibration", "Minute-Bucket Calibration Support")).toBe(2);
    expect(titleTier("calibration", "Reliability diagrams")).toBe(3);
    expect(titleTier("", "Anything")).toBe(3);
  });

  it("puts an exact title match first even when a page scored higher", () => {
    const hits = [{ id: "p1", score: 9 }, { id: "m2", score: 8 }, { id: "m1", score: 7 }, { id: "f1", score: 6 }, { id: "missing", score: 5 }];
    expect(rankHits("Calibration Stability", hits, lookup).map((r) => r.id)).toEqual(["m1", "p1", "m2", "f1"]);
    expect(rankHits("calibration", hits, lookup).map((r) => r.id)).toEqual(["p1", "m1", "m2", "f1"]);
  });

  it("prefers a page over a module within the same title tier, whatever the fuzzy score", () => {
    const hits = [{ id: "m1", score: 9 }, { id: "p1", score: 1 }];
    expect(rankHits("calibration", hits, lookup).map((r) => r.id)).toEqual(["p1", "m1"]);
  });

  it("orders groups by their best hit when there is a query, and by type otherwise", () => {
    const ranked = rankHits("Calibration Stability", [{ id: "p1", score: 9 }, { id: "m1", score: 7 }, { id: "f1", score: 6 }], lookup);
    expect(groupResults(ranked, "Calibration Stability").map((g) => g.heading)).toEqual(["Modules", "Pages", "Findings"]);
    expect(groupResults(ranked, "").map((g) => g.heading)).toEqual(["Pages", "Findings", "Modules"]);
  });

  it("names three starting points", () => {
    expect(STARTING_POINTS.map((r) => [r.title, r.href])).toEqual([
      ["Calibration", "/analytics/calibration/"],
      ["Retractions", "/evidence/retractions/"],
      ["Paper record", "/paper-trading/"],
    ]);
  });
});
