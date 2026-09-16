import { getResearchAnalyses } from "@/lib/analytics/researchData";
import { describe, expect, it } from "vitest";
import { getDashboardData } from "./dashboardData";

describe("public analytics snapshot normalization", () => {
  const data = getDashboardData();
  it("preserves every published entity and produces unique existing route keys", () => {
    expect(data.entities).toHaveLength(1549);
    expect(new Set(data.entities.map(e => `${e.pack}/${e.slug}`)).size).toBe(1549);
    expect(data.entities.filter(e => e.pack === "nba_players")).toHaveLength(482);
    expect(data.entities.filter(e => e.pack === "calibration" && e.sport === "mlb")).toHaveLength(15);
    expect(data.entities.filter(e => e.pack === "calibration" && e.sport === "soccer")).toHaveLength(11);
    expect(data.entities.find(e => e.pack === "mlb_pitch" && e.slug === "team_kc")).toBeDefined();
    expect(data.entities.every(e => e.metrics.every(m => Number.isFinite(m.value)))).toBe(true);
  });
  it("preserves original verdicts and record counts without claiming unique mechanisms", () => {
    expect(data.mechanisms).toHaveLength(287);
    expect(data.mechanisms.filter(r => r.bucket === "confirmed")).toHaveLength(130);
    expect(data.mechanisms.filter(r => r.bucket === "null")).toHaveLength(126);
    expect(data.mechanisms.filter(r => r.bucket === "not_testable")).toHaveLength(31);
    expect(new Set(data.mechanisms.map(r => r.sport)).size).toBe(4);
    expect(data.mechanisms.some(r => r.effect === null)).toBe(true);
  });
  it("does not manufacture scores for totals or additional months", () => {
    const totals = data.markets.find(m => m.id === "mlb_total")!;
    expect(totals.scored).toBe(false);
    expect(totals.model_brier).toBeUndefined();
    expect(totals.reason).toContain("no resolved outcome");
    expect(data.history).toHaveLength(4);
    expect(data.history.find(p => p.sport === "mlb" && p.month === "2026-06")?.model_brier).toBe(.2404);
    expect(data.markets.find(m => m.id === "mlb_moneyline")?.n_rows).toBe(78986);
  });
  it("keeps distinct pitch denominators and all catalog modules", () => {
    expect(data.modules).toHaveLength(76);
    expect(data.pitches.distribution.find(p => p.pitch_type === "FF")?.n).toBe(220235);
    expect(data.pitches.velocity.find(p => p.pitch_type === "FF")?.n).toBe(220233);
    expect(data.coverage.rates).toHaveLength(28);
    expect(data.coverage.histogram.reduce((sum, bin) => sum + bin.dossiers, 0)).toBe(data.coverage.n);
    expect(data.coverage.medianCategories).toBe(18);
    expect(data.coverage.medianCategoriesShare).toBe(0.642857);
    expect(data.coverage.publishedCompletenessScore).toBe(0.464);
    expect(data.benchmarks).toHaveLength(17);
    expect(data.walkForward.folds).toHaveLength(3);
    expect(data.walkForward.brier_mean).toBeCloseTo(.1930064);
  });
  it("exposes derived analyses and orders recent entries by published source date", () => {
    expect(data.analyses).toHaveLength(getResearchAnalyses().length);
    expect(data.recentAnalyses).toHaveLength(6);
    expect(data.recentAnalyses.every(analysis => data.analyses.some(all => all.id === analysis.id))).toBe(true);
    expect(data.recentAnalyses.map(analysis => analysis.asOf)).toEqual([...data.recentAnalyses].map(analysis => analysis.asOf).sort((left, right) => (right || "").localeCompare(left || "")));
  });
});
