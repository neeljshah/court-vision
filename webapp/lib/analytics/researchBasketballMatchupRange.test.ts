import { describe, expect, it } from "vitest";
import {
  buildBasketballMatchupRangeResearch,
  getBasketballMatchupRangeResearch,
  type MatchupRangePair,
} from "./researchBasketballMatchupRange";

const source = (pairings: MatchupRangePair[]) => ({
  input_coverage: { games_total: 4, seasons: ["test"], date_max: "2026-01-01" },
  mask: { min_meetings: 2 },
  pairings,
});
const reciprocal = (row: string, col: string, total: unknown, meetings: unknown): MatchupRangePair[] => [
  { row, col, mean_total: total, n_meetings: meetings },
  { row: col, col: row, mean_total: total, n_meetings: meetings },
];

describe("NBA opponent mean-total range research", () => {
  it("covers every public team and its 29 opponents", () => {
    const analysis = getBasketballMatchupRangeResearch()[0];
    expect(analysis.id).toBe("nba-opponent-total-range");
    expect(analysis.rows).toHaveLength(30);
    expect(analysis.rows.every(row => row.values.opponents === 29)).toBe(true);
    expect(analysis.rows.every(row => row.note?.startsWith("Team: "))).toBe(true);
    expect(analysis.rows.find(row => row.label === "ATL")?.note).toContain("Team: Atlanta Hawks.");
    expect(analysis.scope).toContain("atlas_nba_teams_manifest");
    expect(analysis.caveat).toContain("Seasons and venues are pooled");
    expect(analysis.caveat).toContain("serialized to two decimals");
    expect(analysis.scope).toContain("latest input date 2026-04-12");
    expect(analysis.asOf).toBeUndefined();
    expect(`${analysis.title} ${analysis.description} ${analysis.interpretation}`.toLowerCase()).not.toContain("volatility");
    expect(analysis.fields.slice(-3).map(field => [field.key, field.label, field.digits])).toEqual([
      ["meeting_weighted_mean_total", "Meeting-weighted mean combined total", 2],
      ["between_opponent_mean_total_sd", "Between-opponent mean-total SD", 2],
      ["meetings_across_pairings", "Team-meetings across included pairings", 0],
    ]);
  });

  it("preserves the ATL and BOS extrema, support, and arithmetic", () => {
    const rows = getBasketballMatchupRangeResearch()[0].rows;
    const atl = rows.find(row => row.label === "ATL")!;
    expect(atl.values).toMatchObject({ high_mean_total: 255.7, low_mean_total: 221.5, high_meetings: 10, low_meetings: 6, opponents: 29, meetings_across_pairings: 239 });
    expect(atl.values.total_range).toBeCloseTo(34.2, 10);
    expect(atl.values.meeting_weighted_mean_total).toBeCloseTo(236.98301255230132, 12);
    expect(atl.values.between_opponent_mean_total_sd).toBeCloseTo(9.100866994186187, 12);
    expect(atl.note).toContain("Highest opponent endpoint: IND");
    expect(atl.note).toContain("Lowest opponent endpoint: HOU");
    const bos = rows.find(row => row.label === "BOS")!;
    expect(bos.values).toMatchObject({ high_mean_total: 238.08, low_mean_total: 212.33, high_meetings: 12, low_meetings: 6, meetings_across_pairings: 246 });
    expect(bos.values.total_range).toBeCloseTo(25.75, 10);
    expect(bos.values.meeting_weighted_mean_total).toBeCloseTo(225.05264227642277, 12);
    expect(bos.values.between_opponent_mean_total_sd).toBeCloseTo(5.542856745808446, 12);
    const nyk = rows.find(row => row.label === "NYK")!;
    expect(nyk.values).toMatchObject({ high_mean_total: 237, high_meetings: 6 });
    expect(nyk.note).toContain("DEN (6 meetings), IND (10 meetings)");
    const phi = rows.find(row => row.label === "PHI")!;
    expect(phi.values.meetings_across_pairings).toBe(239);
    expect(phi.values.between_opponent_mean_total_sd).toBeCloseTo(9.776898213520694, 12);
    const was = rows.find(row => row.label === "WAS")!;
    expect(was.values.meetings_across_pairings).toBe(237);
    expect(was.values.between_opponent_mean_total_sd).toBeCloseTo(5.4363393772759645, 12);
  });

  it("keeps zero totals but rejects missing, nonfinite, and invalid support", () => {
    const valid = [...reciprocal("A", "B", 0, 2), ...reciprocal("A", "C", 10, 3)];
    const invalid = [
      ...reciprocal("A", "D", null, 2), ...reciprocal("A", "E", Infinity, 2),
      ...reciprocal("A", "F", 20, 0), ...reciprocal("A", "G", 20, 2.5), ...reciprocal("A", "H", 20, 1),
      ...reciprocal("A", "I", 20, Number.MAX_SAFE_INTEGER + 1),
    ];
    const row = buildBasketballMatchupRangeResearch(source([...valid, ...invalid]))[0].rows.find(item => item.label === "A")!;
    expect(row.values).toMatchObject({ total_range: 10, low_mean_total: 0, high_mean_total: 10, opponents: 2, meeting_weighted_mean_total: 6, meetings_across_pairings: 5 });
    expect(row.values.between_opponent_mean_total_sd).toBeCloseTo(Math.sqrt(24), 12);
    expect(row.note).toContain("Lowest opponent endpoint: B");
  });

  it("uses frequency weights and returns zero SD for constant opponent means", () => {
    const equal = buildBasketballMatchupRangeResearch(source([
      ...reciprocal("A", "B", 0, 2), ...reciprocal("A", "C", 10, 2),
    ]))[0].rows.find(item => item.label === "A")!;
    expect(equal.values).toMatchObject({ meeting_weighted_mean_total: 5, meetings_across_pairings: 4 });
    expect(equal.values.between_opponent_mean_total_sd).toBeCloseTo(5, 12);
    const constant = buildBasketballMatchupRangeResearch(source([
      ...reciprocal("A", "B", 0.1, 3), ...reciprocal("A", "C", 0.1, 4),
    ]))[0].rows.find(item => item.label === "A")!;
    expect(constant.values).toMatchObject({ meeting_weighted_mean_total: 0.1, between_opponent_mean_total_sd: 0, meetings_across_pairings: 7 });
  });

  it("breaks endpoint ties deterministically and excludes incompatible duplicates or reciprocals", () => {
    const pairs = [
      ...reciprocal("A", "C", 10, 2), ...reciprocal("A", "B", 10, 2),
      ...reciprocal("A", "D", 20, 3), ...reciprocal("A", "E", 20, 3),
      { row: "A", col: "X", mean_total: 30, n_meetings: 2 },
      { row: "X", col: "A", mean_total: 31, n_meetings: 2 },
      { row: "A", col: "Y", mean_total: 40, n_meetings: 2 },
      { row: "A", col: "Y", mean_total: 41, n_meetings: 2 },
      { row: "Y", col: "A", mean_total: 40, n_meetings: 2 },
      { row: "A", col: "A", mean_total: 99, n_meetings: 2 },
    ];
    const row = buildBasketballMatchupRangeResearch(source(pairs))[0].rows.find(item => item.label === "A")!;
    expect(row.values).toMatchObject({ low_mean_total: 10, high_mean_total: 20, opponents: 4, meeting_weighted_mean_total: 16, meetings_across_pairings: 10 });
    expect(row.values.between_opponent_mean_total_sd).toBeCloseTo(Math.sqrt(24), 12);
    expect(row.note).toContain("Lowest opponent endpoints: B (2 meetings), C (2 meetings)");
    expect(row.note).toContain("Highest opponent endpoints: D (3 meetings), E (3 meetings)");
  });

  it("returns null derived moments when finite inputs overflow their arithmetic", () => {
    const row = buildBasketballMatchupRangeResearch(source([
      ...reciprocal("A", "B", Number.MAX_VALUE, 2),
      ...reciprocal("A", "C", Number.MAX_VALUE / 2, 2),
    ]))[0].rows.find(item => item.label === "A")!;
    expect(row.values).toMatchObject({ meeting_weighted_mean_total: null, between_opponent_mean_total_sd: null, meetings_across_pairings: 4 });
  });

  it("fails closed when the published meeting floor is absent or malformed", () => {
    const pairings = [...reciprocal("A", "B", 10, 2), ...reciprocal("A", "C", 20, 2)];
    for (const min_meetings of [undefined, null, 1, 2.5, "2"]) {
      const result = buildBasketballMatchupRangeResearch({ pairings, mask: { min_meetings } })[0];
      expect(result.rows).toEqual([]);
      expect(result.scope).toContain("Source meeting floor is unavailable or invalid");
    }
    const rollover = buildBasketballMatchupRangeResearch({
      ...source(pairings), input_coverage: { games_total: 4, seasons: ["test"], date_max: "2026-02-30" },
    })[0];
    expect(rollover.rows).toHaveLength(1);
    expect(rollover.scope).not.toContain("2026-02-30");
  });

  it("retains evidence without inventing missing, invalid, or ambiguous team names", () => {
    const pairings = [...reciprocal("A", "B", 10, 2), ...reciprocal("A", "C", 20, 2)];
    const base = buildBasketballMatchupRangeResearch(source(pairings))[0].rows[0];
    expect(base.note).not.toContain("Team:");
    expect(base.note).not.toContain("undefined");
    const ambiguous = buildBasketballMatchupRangeResearch(source(pairings), { entries: [
      { entity: "A", key_numbers: { team_full_name: "Alpha" } },
      { entity: "A", key_numbers: { team_full_name: "Another Alpha" } },
      { entity: "B", key_numbers: { team_full_name: { invalid: true } } },
    ] })[0].rows[0];
    expect(ambiguous.values).toEqual(base.values);
    expect(ambiguous.note).toEqual(base.note);
    for (const team_full_name of [{ invalid: true }, "   ", undefined]) {
      const invalid = buildBasketballMatchupRangeResearch(source(pairings), { entries: [
        { entity: "A", key_numbers: { team_full_name } },
      ] })[0].rows[0];
      expect(invalid.values).toEqual(base.values);
      expect(invalid.note).toEqual(base.note);
    }
  });
});
