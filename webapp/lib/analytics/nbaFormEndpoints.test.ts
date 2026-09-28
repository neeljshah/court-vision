import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { buildNbaFormRows, NBA_FORM_FIELDS } from "./nbaFormEndpoints";

const published = JSON.parse(readFileSync(join(process.cwd(), "public/data/showcase/nba_form_curves.json"), "utf8"));
const fixtureRow = (changes: Record<string, unknown> = {}) => ({
  player_name: "Test Player", first_form: 10, last_form: 12, delta: 2,
  last_form_league_pctile: 50, n_qual_games: 20, qual_minutes: 200,
  first_date: "2024-02-28", last_date: "2024-03-01", ...changes,
});
const one = (changes: Record<string, unknown> = {}) =>
  buildNbaFormRows({ top_movers_risers: [fixtureRow(changes)], top_movers_fallers: [] })[0];

describe("NBA form endpoint rows", () => {
  it("defines the existing six fields followed by the endpoint and support fields", () => {
    expect(NBA_FORM_FIELDS).toEqual([
      { key: "relative_change", label: "Endpoint relative change", unit: "percent", digits: 2 },
      { key: "delta", label: "Recomputed endpoint change", unit: "number", digits: 3 },
      { key: "first", label: "First 10-game composite", unit: "number", digits: 3 },
      { key: "last", label: "Last 10-game composite", unit: "number", digits: 3 },
      { key: "last_percentile", label: "Last league percentile", unit: "percent", digits: 2 },
      { key: "games", label: "Qualifying games", unit: "number", digits: 0 },
      { key: "endpoint_days", label: "Days between window ends", unit: "number", digits: 0 },
      { key: "qual_minutes", label: "Qualifying minutes", unit: "number", digits: 1 },
      { key: "source_delta", label: "Published endpoint change", unit: "number", digits: 3 },
    ]);
  });

  it("keeps all 30 published rows in source order with exact operand paths", () => {
    const rows = buildNbaFormRows(published);
    expect(rows).toHaveLength(30);
    expect(rows.map(row => row.id)).toEqual(Array.from({ length: 30 }, (_, i) => `form-${i}`));
    expect(rows.slice(0, 15).every(row => row.group === "Published risers")).toBe(true);
    expect(rows.slice(15).every(row => row.group === "Published fallers")).toBe(true);
    expect(rows[0]).toMatchObject({ label: "Victor Wembanyama", values: {
      first: 18.048, last: 37.869, source_delta: 19.821, games: 179,
      qual_minutes: 5429.9, last_percentile: 1, endpoint_days: 880,
    }, bindingValues: { first_window_end: "2023-11-12", last_window_end: "2026-04-10" } });
    expect(rows[0].values.delta).toBeCloseTo(19.821, 12);
    expect(rows[0].values.relative_change).toBeCloseTo(19.821 / 18.048, 12);
    expect(rows[0].sourcePaths).toEqual([
      "top_movers_risers[0].first_form", "top_movers_risers[0].last_form",
      "top_movers_risers[0].delta", "top_movers_risers[0].last_form_league_pctile",
      "top_movers_risers[0].n_qual_games", "top_movers_risers[0].qual_minutes",
      "top_movers_risers[0].first_date", "top_movers_risers[0].last_date",
    ]);
    const eugene = rows.find(row => row.label === "Eugene Omoruyi")!;
    expect(eugene).toMatchObject({ id: "form-16", group: "Published fallers", values: {
      endpoint_days: 52, games: 23, qual_minutes: 306, source_delta: -10.211,
    } });
    expect(eugene.sourcePaths?.[0]).toBe("top_movers_fallers[1].first_form");
    expect(eugene.note).toContain("ends of the first and last retained 10-game windows");
    expect(eugene.note).toContain("all games meeting the 8-minute floor");
    expect(rows.every(row => row.windows === undefined && row.bindingValues !== undefined)).toBe(true);
  });

  it("preserves published changes independently of subtraction on four rounded rows", () => {
    const rows = buildNbaFormRows(published);
    const differing = rows.filter(row => Math.abs((row.values.delta ?? 0) - (row.values.source_delta ?? 0)) > 0.0005);
    expect(differing.map(row => row.label)).toEqual(["Myles Turner", "Moritz Wagner", "Tre Mann", "Jalen Smith"]);
    expect(differing.map(row => Number(row.values.delta?.toFixed(3)))).toEqual([-11.044, -9.127, -8.941, -7.762]);
    expect(differing.map(row => row.values.source_delta)).toEqual([-11.043, -9.126, -8.942, -7.761]);
    expect(one({ delta: null }).values).toMatchObject({ first: 10, last: 12, delta: 2, source_delta: null });
    expect(one({ first_form: null, delta: 7 }).values).toMatchObject({ first: null, delta: null, relative_change: null, source_delta: 7 });
  });

  it("uses UTC calendar days across leap day and daylight saving transitions", () => {
    expect(one().values.endpoint_days).toBe(2);
    expect(one({ first_date: "2024-03-09", last_date: "2024-03-11" }).values.endpoint_days).toBe(2);
    expect(one({ first_date: "2024-11-02", last_date: "2024-11-04" }).values.endpoint_days).toBe(2);
    expect(one({ first_date: "2024-03-01", last_date: "2024-03-01" }).values.endpoint_days).toBe(0);
  });

  it.each([
    ["2023-02-29", "2024-03-01"], ["2024-02-30", "2024-03-01"],
    ["2024-1-01", "2024-03-01"], ["2024-03-01T00:00:00Z", "2024-03-01"],
    [null, "2024-03-01"], ["2024-03-02", "2024-03-01"],
  ])("makes invalid or reversed endpoint dates unavailable: %s to %s", (first_date, last_date) => {
    const row = one({ first_date, last_date });
    expect(row.values.endpoint_days).toBeNull();
    expect(row.bindingValues).toEqual({
      first_window_end: typeof first_date === "string" && /^2024-03-02$/.test(first_date) ? first_date : null,
      last_window_end: last_date,
    });
  });

  it("keeps zero values and nulls malformed numeric measurements", () => {
    expect(one({ first_form: 0, last_form: 0, delta: 0, last_form_league_pctile: 0,
      n_qual_games: 0, qual_minutes: 0 }).values).toEqual({
      relative_change: null, delta: 0, first: 0, last: 0, last_percentile: 0,
      games: 0, endpoint_days: 2, qual_minutes: 0, source_delta: 0,
    });
    expect(one({ first_form: "10", last_form: Infinity, delta: NaN, last_form_league_pctile: 101,
      n_qual_games: 1.5, qual_minutes: -1 }).values).toEqual({
      relative_change: null, delta: null, first: null, last: null, last_percentile: null,
      games: null, endpoint_days: 2, qual_minutes: null, source_delta: null,
    });
    expect(one({ last_form_league_pctile: -1, n_qual_games: Number.MAX_SAFE_INTEGER + 1 }).values).toMatchObject({
      last_percentile: null, games: null,
    });
    expect(buildNbaFormRows(null)).toEqual([]);
    expect(buildNbaFormRows({ top_movers_risers: [null], top_movers_fallers: [] })).toEqual([]);
  });

  it("keeps overflowing derived values unavailable while preserving finite source measurements", () => {
    expect(one({ first_form: -Number.MAX_VALUE, last_form: Number.MAX_VALUE }).values).toMatchObject({ delta: null, relative_change: null, source_delta: 2 });
    expect(one({ first_form: Number.MIN_VALUE, last_form: 1 }).values).toMatchObject({ delta: 1, relative_change: null });
  });
});
