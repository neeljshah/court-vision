import { describe, expect, it } from "vitest";
import type { LabRow } from "./labTypes";
import { summarizeScatter } from "./scatterSummary";

const row = (id: string, group: string, values: Record<string, number | null>): LabRow => ({
  id, label: id, group, values,
});

describe("summarizeScatter", () => {
  it("keeps disjoint support counts and contrasts paired with all-available medians", () => {
    const rows = [
      row("x-only", "All", { x: -2, y: null }),
      row("paired-zero", "All", { x: 0, y: 0 }),
      row("paired-positive", "All", { x: 2, y: 4 }),
      row("y-only", "All", { x: null, y: 6 }),
      row("neither", "All", { x: null, y: null }),
    ];
    const summary = summarizeScatter(rows, "x", "y");
    expect(summary).toMatchObject({
      total: 5, paired: 2, xOnly: 1, yOnly: 1, neither: 1,
      x: { measured: 3, pairedMedian: 1, allMedian: 0 },
      y: { measured: 3, pairedMedian: 2, allMedian: 4 },
    });
    expect(summary.pairedRows.map(item => item.id)).toEqual(["paired-zero", "paired-positive"]);
    expect(summary.paired + summary.xOnly + summary.yOnly + summary.neither).toBe(summary.total);
  });

  it("returns null medians and zero counts for an empty population", () => {
    expect(summarizeScatter([], "x", "y")).toEqual({
      total: 0, paired: 0, xOnly: 0, yOnly: 0, neither: 0, pairedRows: [],
      x: { measured: 0, pairedMedian: null, allMedian: null },
      y: { measured: 0, pairedMedian: null, allMedian: null },
    });
  });

  it("keeps all-available medians when no rows are paired", () => {
    const summary = summarizeScatter([
      row("x", "All", { x: 3, y: null }),
      row("y", "All", { x: null, y: -5 }),
      row("none", "All", { x: null, y: null }),
    ], "x", "y");
    expect(summary).toMatchObject({
      total: 3, paired: 0, xOnly: 1, yOnly: 1, neither: 1,
      x: { measured: 1, pairedMedian: null, allMedian: 3 },
      y: { measured: 1, pairedMedian: null, allMedian: -5 },
    });
  });

  it("handles one paired row and constant paired values", () => {
    const singleton = summarizeScatter([row("one", "All", { x: -4, y: 0 })], "x", "y");
    expect(singleton.x).toEqual({ measured: 1, pairedMedian: -4, allMedian: -4 });
    expect(singleton.y).toEqual({ measured: 1, pairedMedian: 0, allMedian: 0 });

    const constant = summarizeScatter([
      row("a", "All", { x: 5, y: -1 }),
      row("b", "All", { x: 5, y: -1 }),
    ], "x", "y");
    expect(constant.x).toEqual({ measured: 2, pairedMedian: 5, allMedian: 5 });
    expect(constant.y).toEqual({ measured: 2, pairedMedian: -1, allMedian: -1 });
  });

  it("counts each row once when both axes use the same key", () => {
    const summary = summarizeScatter([
      row("negative", "All", { value: -2 }),
      row("zero", "All", { value: 0 }),
      row("missing", "All", { value: null }),
      row("nonfinite", "All", { value: Infinity }),
    ], "value", "value");
    expect(summary).toMatchObject({
      total: 4, paired: 2, xOnly: 0, yOnly: 0, neither: 2,
      x: { measured: 2, pairedMedian: -1, allMedian: -1 },
      y: { measured: 2, pairedMedian: -1, allMedian: -1 },
    });
  });

  it("rejects malformed, nonfinite, and absent runtime values", () => {
    const summary = summarizeScatter([
      row("string-x", "All", { x: "1" as unknown as number, y: 1 }),
      row("nan-y", "All", { x: 2, y: NaN }),
      row("infinite", "All", { x: -Infinity, y: Infinity }),
      row("absent", "All", {}),
    ], "x", "y");
    expect(summary).toMatchObject({ total: 4, paired: 0, xOnly: 1, yOnly: 1, neither: 2 });
    expect(summary.pairedRows).toEqual([]);
  });

  it("uses only the supplied cohort while preserving rows and paired-row order", () => {
    const rows = [
      row("east-a", "East", { x: 1, y: 2 }),
      row("west", "West", { x: 3, y: 4 }),
      row("east-b", "East", { x: 5, y: 6 }),
    ];
    const original = structuredClone(rows);
    const east = rows.filter(item => item.group === "East");
    const summary = summarizeScatter(east, "x", "y");
    expect(summary).toMatchObject({ total: 2, paired: 2, xOnly: 0, yOnly: 0, neither: 0 });
    expect(summary.pairedRows.map(item => item.id)).toEqual(["east-a", "east-b"]);
    expect(rows).toEqual(original);
    expect(east).toEqual([rows[0], rows[2]]);
  });
});
