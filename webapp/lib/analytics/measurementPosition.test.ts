import { describe, expect, it } from "vitest";
import type { LabRow } from "./labTypes";
import { summarizeMeasurementPosition } from "./measurementPosition";
import { getSoccerFormGapResearch } from "./researchSoccerFormGap";

const rows = (values: unknown[]): LabRow[] => values.map((value, index) => ({
  id: String(index),
  label: `Row ${index}`,
  group: "Fixture",
  values: { metric: value as number | null },
}));

describe("summarizeMeasurementPosition", () => {
  it("counts strict position and exact ties while excluding missing and malformed values", () => {
    const cohort = rows([1, 2, 2, 3, null, NaN, Infinity, "2"]);
    expect(summarizeMeasurementPosition(cohort, "metric", cohort[1])).toEqual({
      available: true,
      total: 8,
      measured: 4,
      missing: 4,
      value: 2,
      below: 1,
      equal: 2,
      above: 1,
      median: 2,
      differenceFromMedian: 0,
    });
  });

  it("preserves zero and negative measurements and cleans subtraction noise", () => {
    const cohort = rows([-0.3, 0, 0.1, 0.2]);
    expect(summarizeMeasurementPosition(cohort, "metric", cohort[2])).toMatchObject({
      available: true,
      value: 0.1,
      below: 2,
      equal: 1,
      above: 1,
      median: 0.05,
      differenceFromMedian: 0.05,
    });
    expect(summarizeMeasurementPosition(rows([-2, 0, 3]), "metric", rows([-2, 0, 3])[1]))
      .toMatchObject({ available: true, value: 0, below: 1, equal: 1, above: 1, median: 0 });
  });

  it("handles singleton and all-missing cohorts without invented position", () => {
    const singleton = rows([-4]);
    expect(summarizeMeasurementPosition(singleton, "metric", singleton[0])).toMatchObject({
      available: true,
      total: 1,
      measured: 1,
      missing: 0,
      value: -4,
      below: 0,
      equal: 1,
      above: 0,
      median: -4,
      differenceFromMedian: 0,
    });

    const missing = rows([null, NaN]);
    expect(summarizeMeasurementPosition(missing, "metric", missing[0])).toEqual({
      available: false,
      total: 2,
      measured: 0,
      missing: 2,
      value: null,
      below: 0,
      equal: 0,
      above: 0,
      median: null,
      differenceFromMedian: null,
    });
  });

  it("does not fabricate membership for absent, duplicate, or mismatched selections", () => {
    const cohort = rows([1, 2, 3]);
    const absent = { ...cohort[1], id: "absent" };
    const mismatched = { ...cohort[1], values: { metric: 2.5 } };
    const duplicated = [...cohort, { ...cohort[1] }];

    for (const result of [
      summarizeMeasurementPosition(cohort, "metric", absent),
      summarizeMeasurementPosition(cohort, "metric", mismatched),
      summarizeMeasurementPosition(duplicated, "metric", cohort[1]),
    ]) {
      expect(result).toMatchObject({
        available: false,
        value: null,
        below: 0,
        equal: 0,
        above: 0,
        differenceFromMedian: null,
      });
    }
  });

  it("places published Brest and Bologna values in the full soccer cohort", () => {
    const analysis = getSoccerFormGapResearch()[0];
    const brest = analysis.rows.find(row => row.label === "Brest")!;
    const bologna = analysis.rows.find(row => row.label === "Bologna")!;
    const brestPosition = summarizeMeasurementPosition(analysis.rows, "home_minus_away_ppg", brest);
    const bolognaPosition = summarizeMeasurementPosition(analysis.rows, "home_minus_away_ppg", bologna);

    expect(brestPosition).toMatchObject({ available: true, total: 187, measured: 187, missing: 0, value: 1.3 });
    expect(bolognaPosition).toMatchObject({ available: true, total: 187, measured: 187, missing: 0, value: -1.5 });
    expect(brestPosition.below + brestPosition.equal + brestPosition.above).toBe(187);
    expect(bolognaPosition.below + bolognaPosition.equal + bolognaPosition.above).toBe(187);
    expect(brestPosition.below).toBeGreaterThan(bolognaPosition.below);
  });

  it("returns no unbounded difference when finite endpoints overflow subtraction", () => {
    const cohort = rows([-Number.MAX_VALUE, Number.MAX_VALUE]);
    expect(summarizeMeasurementPosition(cohort, "metric", cohort[1])).toMatchObject({
      available: true,
      median: 0,
      differenceFromMedian: Number.MAX_VALUE,
    });
    const skewed = rows([-Number.MAX_VALUE, -Number.MAX_VALUE, Number.MAX_VALUE]);
    expect(summarizeMeasurementPosition(skewed, "metric", skewed[2]).differenceFromMedian).toBeNull();
  });
});
