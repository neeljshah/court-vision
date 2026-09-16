import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { loadCrossSportComparability } from "./crossSportComparability.server";
import type { CrossSportSnapshot } from "./crossSportComparability";

function publishedSnapshot(): CrossSportSnapshot {
  const path = join(process.cwd(), "public", "data", "showcase", "kernel_transfer.json");
  return JSON.parse(readFileSync(path, "utf8")) as CrossSportSnapshot;
}

describe("cross-sport comparability", () => {
  it("keeps the five published rows split into two supported and three unsupported comparisons", () => {
    const data = loadCrossSportComparability();
    expect(data.rows).toHaveLength(5);
    expect(data.comparableRows.map(row => row.sport)).toEqual(["mlb", "soccer_intl"]);
    expect(data.unsupportedRows).toHaveLength(3);
  });

  it("preserves unavailable published values as null rather than coercing them to zero", () => {
    const nba = loadCrossSportComparability().rows.find(row => row.sport === "nba")!;
    expect(nba.reliability_model).toBeNull();
    expect(nba.reliability_market).toBeNull();
    expect(nba.reliability_gap).toBeNull();
    expect(loadCrossSportComparability().capabilities.find(row => row.sport === "nba")?.scoreAvailable).toBe(false);
  });

  it("keeps each unsupported comparability reason verbatim", () => {
    const expected = publishedSnapshot().rows.filter(row => !row.reliability_comparable).map(row => row.comparability_reason);
    expect(loadCrossSportComparability().unsupportedRows.map(row => row.comparability_reason)).toEqual(expected);
  });
});
