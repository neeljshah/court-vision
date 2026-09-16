import { describe, expect, it } from "vitest";
import type { LabField, LabRow } from "./labTypes";
import { summarizeMeasurementCoverage } from "./measurementCoverage";
import { getNbaPlayerContextResearch } from "./researchNbaPlayerContext";
import { getNbaTeamProfileResearch } from "./researchNbaTeamProfile";

const fields: LabField[] = [
  { key: "a", label: "Alpha", unit: "number" },
  { key: "b", label: "Beta", unit: "number" },
];
const row = (id: string, group: string, values: Record<string, number | null>): LabRow => ({
  id, label: id, group, values,
});

describe("summarizeMeasurementCoverage", () => {
  it("counts finite zero and negative values while rejecting missing and malformed values", () => {
    const rows = [
      row("zero", "All", { a: 0, b: -2 }),
      row("null", "All", { a: null, b: NaN }),
      row("infinite", "All", { a: Infinity, b: -Infinity }),
      row("missing", "All", { b: 3 }),
      row("string", "All", { a: "4" as unknown as number, b: 4 }),
    ];
    expect(summarizeMeasurementCoverage(rows, fields)).toEqual([
      { key: "a", label: "Alpha", total: 5, measured: 1, missing: 4, share: 0.2 },
      { key: "b", label: "Beta", total: 5, measured: 3, missing: 2, share: 0.6 },
    ]);
  });

  it("returns null shares for an empty population without dropping fields", () => {
    expect(summarizeMeasurementCoverage([], fields)).toEqual([
      { key: "a", label: "Alpha", total: 0, measured: 0, missing: 0, share: null },
      { key: "b", label: "Beta", total: 0, measured: 0, missing: 0, share: null },
    ]);
  });

  it("uses the supplied cohort as the exact denominator", () => {
    const allRows = [
      row("east-1", "East", { a: 1, b: null }),
      row("east-2", "East", { a: null, b: 2 }),
      row("west-1", "West", { a: 3, b: 3 }),
    ];
    const east = allRows.filter(item => item.group === "East");
    expect(summarizeMeasurementCoverage(east, fields)).toEqual([
      { key: "a", label: "Alpha", total: 2, measured: 1, missing: 1, share: 0.5 },
      { key: "b", label: "Beta", total: 2, measured: 1, missing: 1, share: 0.5 },
    ]);
  });

  it("preserves field order and does not mutate either input", () => {
    const ordered = [fields[1], fields[0]];
    const rows = [row("one", "All", { a: 1, b: 2 })];
    const originalRows = structuredClone(rows);
    const originalFields = structuredClone(ordered);
    const result = summarizeMeasurementCoverage(rows, ordered);
    expect(result.map(item => item.key)).toEqual(["b", "a"]);
    expect(rows).toEqual(originalRows);
    expect(ordered).toEqual(originalFields);
  });

  it("reports the sparse published composite fields against their full populations", () => {
    const players = getNbaPlayerContextResearch()[0];
    const playerCoverage = summarizeMeasurementCoverage(players.rows, players.fields);
    expect(playerCoverage.find(item => item.key === "consistency_cv")).toMatchObject({ total: 156, measured: 25, missing: 131 });
    expect(playerCoverage.find(item => item.key === "q4_rebounds_shift")).toMatchObject({ total: 156, measured: 13, missing: 143 });
    expect(playerCoverage.find(item => item.key === "career_points_per36")).toMatchObject({ total: 156, measured: 154, missing: 2 });

    const teams = getNbaTeamProfileResearch()[0];
    const teamCoverage = summarizeMeasurementCoverage(teams.rows, teams.fields);
    expect(teamCoverage.find(item => item.key === "pace_proxy")).toMatchObject({ total: 30, measured: 30, missing: 0, share: 1 });
    // every team sits below the published halftime split floor, so the masked margin never counts as measured
    expect(teamCoverage.find(item => item.key === "comeback_second_half_margin")).toMatchObject({ total: 30, measured: 0, missing: 30, share: 0 });
  });
});
