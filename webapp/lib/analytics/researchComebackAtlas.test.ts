import { describe, expect, it } from "vitest";
import { buildComebackAtlasResearch } from "./researchComebackAtlas";
import published from "../../public/data/showcase/comeback_atlas.json";
import { buildLabCSV } from "../../components/analytics/lab/LabTable";

const cell = (lead_band: string, time_band: string, outcome_rate: number, n_games = 40) => ({ lead_band, time_band, outcome_rate, n_games, n_ticks: 200, masked_n_lt_30: n_games < 30 });

describe("comeback atlas research", () => {
  it("uses the home-win complement when the home side leads", () => {
    const analysis = buildComebackAtlasResearch({ cells: [cell("lead_+01_05", "rem_00_02", 0.8)] })[0];
    expect(analysis).toMatchObject({ id: "comeback-rates-deficit-time", source: "comeback_atlas" });
    expect(analysis.rows[0].values).toMatchObject({ comeback_share: 0.2, leading_side_outcome_share: 0.8, games: 40, ticks: 200 });
    expect(analysis.rows[0].sourcePaths).toContain("cells[].outcome_rate");
    expect(analysis.bindings?.every(binding => binding.valueKey in analysis.rows[0].values || binding.valueKey in (analysis.rows[0].bindingValues || {}))).toBe(true);
  });

  it("orders deficit-time cells deterministically and retains flagged support", () => {
    const rows = buildComebackAtlasResearch({ cells: [cell("lead_+06_10", "rem_05_12", 0.9), cell("lead_+01_05", "rem_00_02", 0.8, 20)] })[0].rows;
    expect(rows.map(row => row.label)).toEqual(["Home leads 1-5 | 0-2 remaining", "Home leads 6-10 | 5-12 remaining"]);
    expect(rows[0].note).toContain("Small-support source cell");
  });

  it("uses home-win frequency when the home side trails and preserves the raw operand", () => {
    const analysis = buildComebackAtlasResearch({ cells: [cell("lead_-01_05", "rem_00_02", 0.0129)] })[0];
    const row = analysis.rows[0];
    expect(row.label).toBe("Home trails 1-5 | 0-2 remaining");
    expect(row.values).toMatchObject({ comeback_share: 0.0129, leading_side_outcome_share: 0.9871 });
    expect(row.bindingValues?.outcome_rate).toBe(0.0129);
    expect(analysis.bindings?.find(binding => binding.operand === "outcome_rate")?.valueKey).toBe("outcome_rate");
    expect(row.note).toContain("Home is trailing");
  });

  it.each(["lead_00", "unpublished", "lead_+10_05", "lead_-00_05"])("leaves side-dependent shares unavailable for %s", lead => {
    const row = buildComebackAtlasResearch({ cells: [cell(lead, "rem_00_02", 0.4452)] })[0].rows[0];
    expect(row.values).toEqual({ comeback_share: null, games: 40, ticks: 200, leading_side_outcome_share: null });
    expect(row.bindingValues?.outcome_rate).toBe(0.4452);
    expect(row.note).toContain("no defined trailing side");
  });

  it("corrects every published signed cell without changing support or masking", () => {
    const analysis = buildComebackAtlasResearch(published)[0];
    expect(analysis.rows).toHaveLength(84);
    for (const sourceCell of published.cells) {
      const row = analysis.rows.find(item => item.id === `comeback-${sourceCell.lead_band}-${sourceCell.time_band}`)!;
      const tied = sourceCell.lead_band === "lead_00";
      const expected = sourceCell.lead_band.startsWith("lead_-") ? sourceCell.outcome_rate : Number((1 - sourceCell.outcome_rate).toFixed(6));
      expect(row.values.comeback_share).toBe(tied ? null : expected);
      expect(row.values.leading_side_outcome_share).toBe(tied ? null : Number((1 - expected).toFixed(6)));
      expect(row.values.games).toBe(sourceCell.n_games);
      expect(row.values.ticks).toBe(sourceCell.n_ticks);
      expect(row.bindingValues?.masked_n_lt_30).toBe(String(sourceCell.masked_n_lt_30));
      expect(row.bindingValues?.outcome_rate).toBe(sourceCell.outcome_rate);
    }
    const trailing = analysis.rows.find(row => row.id === "comeback-lead_-01_05-rem_00_02")!;
    expect(trailing.values.comeback_share).toBe(0.0129);
    const tied = analysis.rows.find(row => row.id === "comeback-lead_00-rem_00_02")!;
    const csv = buildLabCSV(analysis, [trailing, tied]);
    expect(csv).toContain('"Home trails 1-5 | 0-2 remaining"');
    expect(csv).toContain('"Home trails 1-5",0.0129,348,25501,0.9871,');
    expect(csv).toContain('"Tied score | 0-2 remaining","Tied score",,201,775,,');
  });

  it("returns no rows for missing or malformed cells", () => {
    expect(buildComebackAtlasResearch({ cells: [{ ...cell("lead_+01_05", "rem_00_02", 0.8), n_games: -1 }] })[0].rows).toEqual([]);
    expect(buildComebackAtlasResearch({})[0].rows).toEqual([]);
  });
});
