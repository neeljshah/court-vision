import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { basketballResearch } from "./researchBasketball";

const source = (id: string) => JSON.parse(readFileSync(join(process.cwd(), "public/data/showcase", `${id}.json`), "utf8"));

describe("basketballResearch", () => {
  const datasets = basketballResearch();

  it("returns seven complete, source-backed analyses", () => {
    expect(datasets).toHaveLength(7);
    expect(new Set(datasets.map(d => d.id)).size).toBe(7);
    for (const dataset of datasets) {
      expect(dataset.sport).toBe("nba");
      expect(dataset.rows.length).toBeGreaterThan(0);
      expect(dataset.formula).toBeTruthy();
      expect(dataset.interpretation).toBeTruthy();
      expect(dataset.references.every(r => r.url.startsWith("https://www.nba.com/"))).toBe(true);
      expect(() => source(dataset.source)).not.toThrow();
      for (const item of dataset.rows) for (const value of Object.values(item.values)) expect(value === null || Number.isFinite(value)).toBe(true);
    }
  });

  it("computes variability range directly from the three published CV operands", () => {
    const raw = source("nba_consistency_profiles").most_consistent_top15[0];
    const item = datasets.find(d => d.id === "nba-variability-imbalance")!.rows[0];
    const cvs = [raw.pts_cv_shrunk, raw.reb_cv_shrunk, raw.ast_cv_shrunk];
    expect(item.values.cv_range).toBeCloseTo(Math.max(...cvs) - Math.min(...cvs), 12);
    expect(item.values.games).toBe(raw.games);
  });

  it("finds lineup sign reversals and reproduces residual math", () => {
    const dataset = datasets.find(d => d.id === "nba-lineup-expectation-reversals")!;
    const reversal = dataset.rows.find(r => r.values.reversal === 1)!;
    expect(reversal).toBeDefined();
    expect(Math.sign(reversal.values.observed!)).not.toBe(Math.sign(reversal.values.expected!));
    expect(reversal.values.residual).toBeCloseTo(reversal.values.observed! - reversal.values.expected!, 12);
  });

  it("keeps both rim components visible and averages their reductions", () => {
    const dataset = datasets.find(d => d.id === "nba-rim-two-axis-pressure")!;
    const item = dataset.rows[0];
    expect(item.values.frequency_reduction).toBeCloseTo(item.values.share_off! - item.values.share_on!, 12);
    expect(item.values.two_axis_pressure).toBeCloseTo((item.values.frequency_reduction! + item.values.efg_reduction!) / 2, 12);
    const mixed = dataset.rows.find(r => r.values.frequency_reduction! > 0 && r.values.efg_reduction! < 0)!;
    expect(mixed).toBeDefined();
    expect(dataset.fields.find(field => field.key === "two_axis_pressure")?.label).toContain("Equal-weight");
    expect(dataset.interpretation).toContain("either component can offset the other");
    expect(dataset.caveat).toContain("presentation choice");
  });

  it("scales Q4 shifts and endpoint form movement from published endpoints", () => {
    const q4 = datasets.find(d => d.id === "nba-q4-role-redistribution")!.rows[0];
    expect(q4.values.shift).toBeCloseTo(q4.values.q4_rate! - q4.values.early_rate!, 12);
    expect(q4.values.relative_shift).toBeCloseTo(q4.values.shift! / Math.abs(q4.values.early_rate!), 12);
    const form = datasets.find(d => d.id === "nba-form-endpoint-elasticity")!.rows[0];
    expect(form.values.delta).toBeCloseTo(form.values.last! - form.values.first!, 12);
    expect(form.values.last_percentile).toBeGreaterThanOrEqual(0);
    expect(form.values.last_percentile).toBeLessThanOrEqual(1);
  });

  it("does not add overlapping schedule frequencies", () => {
    const dataset = datasets.find(d => d.id === "nba-schedule-compression-profile")!;
    const item = dataset.rows[0];
    const expected = (item.values.b2b! + item.values.three_in_four! + item.values.four_in_six!) / 3;
    expect(item.values.compression).toBeCloseTo(expected, 12);
    expect(item.values.compression).toBeGreaterThanOrEqual(0);
    expect(item.values.compression).toBeLessThanOrEqual(1);
    expect(dataset.fields.find(field => field.key === "compression")?.label).toContain("Equal-weight");
    expect(dataset.caveat).toContain("not a share of distinct games");
    expect(dataset.caveat).toContain("presentation choice");
  });

  it("deduplicates matchup directions and centers contrasts by meeting weight", () => {
    const raw = source("nba_matchup_grid");
    const dataset = datasets.find(d => d.id === "nba-matchup-profile-contrast")!;
    expect(dataset.rows).toHaveLength(raw.pairings.length / 2);
    const weighted = dataset.rows.reduce((sum, r) => sum + r.values.total_vs_pool! * r.values.meetings!, 0);
    expect(weighted).toBeCloseTo(0, 8);
    expect(dataset.rows.every(r => r.values.absolute_margin! >= 0 && r.values.meetings! >= raw.mask.min_meetings)).toBe(true);
    const celticsLakers = dataset.rows.find(r => r.label === "BOS vs LAL")!;
    expect(celticsLakers.note).toContain("Boston Celtics");
    expect(celticsLakers.note).toContain("Los Angeles Lakers");
    expect(dataset.scope).toContain("atlas_nba_teams_manifest");
  });
});
