import { describe, expect, it } from "vitest";
import { getLabData } from "./labData";
import { displayMeasurement, rankedRows } from "./labTypes";
const data = getLabData();
describe("measurement lab source contracts", () => {
  it("preserves literal source values and their units", () => {
    const fatigue = data.datasets.find(d => d.id === "schedule-fatigue")!;
    expect(fatigue.rows).toHaveLength(90);
    const denver = fatigue.rows.find(r => r.label === "DEN" && r.group === "2025-26")!;
    expect(denver.values.sft_credible_pts_per100_ortg).toBe(-.3771);
    expect(displayMeasurement(.218, { key: "b2b", label: "B2B", unit: "percent" })).toBe("21.8%");
    expect(displayMeasurement(-.0618, { key: "delta", label: "Difference", unit: "pp" })).toBe("-6.18 pp");
  });
  it("preserves censoring and empty WTA cohorts instead of zero effects", () => {
    const lhl = data.datasets.find(d => d.id === "line-half-life")!;
    expect(lhl.rows.find(r => r.label === "TENNIS")?.values.half_life_hours).toBeNull();
    expect(lhl.rows.find(r => r.label === "TENNIS")?.note).toContain(">6");
    expect(lhl.rows.find(r => r.label === "TENNIS")?.definition?.observationWindow).toBe("2026-07-03 to 2026-07-17 (15 days)");
    expect(data.datasets.filter(d => d.id.startsWith("tennis-wta")).every(d => d.rows.length === 0)).toBe(true);
  });
  it("carries published comparison definitions into incompatible cohorts", () => {
    const lcf = data.datasets.find(d => d.id === "live-clock")!;
    expect(lcf.rows.map(row => row.definition?.unit)).toEqual(["runs", "goals"]);
    expect(lcf.rows.map(row => row.definition?.clockField)).toEqual(["inning", "minute"]);
    const fatigue = data.datasets.find(d => d.id === "schedule-fatigue")!;
    expect(new Set(fatigue.rows.map(row => row.definition?.season))).toEqual(new Set(["2023-24", "2024-25", "2025-26"]));
    const rim = data.datasets.find(d => d.id === "rim-deterrence")!;
    expect(new Set(rim.rows.map(row => row.definition?.season))).toEqual(new Set(["2024-25", "2025-26"]));
  });
  it("keeps market-foresight checkpoint rows within their published sport windows", () => {
    const foresight = data.datasets.find(dataset => dataset.id === "market-foresight")!;
    const mlbRows = foresight.rows.filter(row => row.definition?.sport === "MLB");
    const soccerRows = foresight.rows.filter(row => row.definition?.sport === "INTERNATIONAL SOCCER");
    expect(mlbRows).toHaveLength(10);
    expect(soccerRows).toHaveLength(19);
    expect(new Set(mlbRows.map(row => row.definition?.observationWindow))).toEqual(new Set(["Checkpoints 1 to 10"]));
    expect(new Set(soccerRows.map(row => row.definition?.observationWindow))).toEqual(new Set(["Checkpoints 0 to 90"]));
  });
  it("keeps both pitch denominators and selected-subset disclosure", () => {
    const ff = data.datasets.find(d => d.id === "pitch-profiles")!.rows.find(r => r.label === "FF")!;
    expect(ff.values.mix_n).toBe(220235);
    expect(ff.values.velocity_n).toBe(220233);
    expect(ff.values.p50).toBe(94.5);
    expect(data.datasets.find(d => d.id === "nba-consistency")?.caveat).toContain("not the complete player population");
  });
  it("has unique rows and no nonfinite numbers in any view", () => {
    expect(new Set(data.datasets.map(d => d.id)).size).toBe(data.datasets.length);
    for (const d of data.datasets) {
      expect(new Set(d.rows.map(r => r.id)).size).toBe(d.rows.length);
      expect(d.rows.every(r => Object.values(r.values).every(v => v === null || Number.isFinite(v)))).toBe(true);
    }
    expect(data.novel).toHaveLength(6);
  });
  it("ranks numeric rows without coercing null and preserves true zero", () => {
    const rows = [{ id: "a", label: "Missing", group: "x", values: { n: null } }, { id: "b", label: "Zero", group: "x", values: { n: 0 } }, { id: "c", label: "Negative", group: "x", values: { n: -1 } }];
    expect(rankedRows(rows, "n", true).map(r => r.id)).toEqual(["c", "b"]);
    expect(displayMeasurement(null, { key: "n", label: "Count", unit: "number" })).toBe("Unavailable");
  });
});
