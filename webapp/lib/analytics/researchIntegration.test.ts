import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { getResearchAnalyses } from "./researchData";

const analyses = getResearchAnalyses();
const sourceRoot = resolve(__dirname, "../../public/data/showcase");

describe("research analysis integration", () => {
  it("keeps the complete public registry structurally safe", () => {
    expect(analyses).toHaveLength(62);
    const ids = analyses.map((analysis) => analysis.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids.every((id) => /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(id))).toBe(true);
    expect(analyses.reduce((total, analysis) => total + analysis.rows.length, 0)).toBe(4477);
    for (const analysis of analyses) {
      const fieldKeys = analysis.fields.map((field) => field.key);
      expect(fieldKeys.length).toBeGreaterThan(0);
      expect(fieldKeys.every((key) => key.trim().length > 0)).toBe(true);
      expect(new Set(fieldKeys).size).toBe(fieldKeys.length);
      expect(analysis.fields.every((field) => field.label.trim().length > 0)).toBe(true);
      const rowIds = analysis.rows.map((row) => row.id);
      expect(rowIds.every((id) => id.trim().length > 0)).toBe(true);
      expect(new Set(rowIds).size).toBe(rowIds.length);
      expect(analysis.rows.every((row) => analysis.fields.every((field) => {
        const value = row.values[field.key];
        return value === null || (typeof value === "number" && Number.isFinite(value));
      }))).toBe(true);
      expect(existsSync(resolve(sourceRoot, `${analysis.source}.json`))).toBe(true);
      if (analysis.asOf) {
        const date = analysis.asOf.slice(0, 10);
        expect(date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
        expect(new Date(`${date}T00:00:00Z`).toISOString().startsWith(date)).toBe(true);
      }
    }
  });

  it("registers the four A3 analyses with row-level published field paths", () => {
    const expected = new Map([
      ["pace-variance-favorite-probability", 24],
      ["star-removal-team-win-probability", 30],
      ["lineup-proxy-active-missed-record", 408],
      ["comeback-rates-deficit-time", 84],
    ]);
    for (const [id, rows] of expected) {
      const analysis = analyses.find((candidate) => candidate.id === id);
      expect(analysis?.rows).toHaveLength(rows);
      expect(analysis?.rows.every((row) => row.sourcePaths?.length)).toBe(true);
    }
  });
});
