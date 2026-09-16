import { describe, expect, it } from "vitest";
import { validationResearch } from "./researchValidation";

const data = validationResearch();
const get = (id: string) => data.find(d => d.id === id)!;

describe("validation research analytics", () => {
  it("exports eight distinct, auditable descriptive questions", () => {
    expect(data).toHaveLength(8);
    expect(new Set(data.map(d => d.id)).size).toBe(8);
    for (const d of data) {
      expect(d.rows.length).toBeGreaterThan(0);
      expect(d.formula).toBeTruthy();
      expect(d.interpretation).toBeTruthy();
      expect(d.caveat.toLowerCase()).not.toContain("positive edge");
      expect(d.novelty).toBe("Derived analysis");
    }
  });

  it("computes signed and relative score gaps from the source operands", () => {
    const mlb = get("brier-relative-gap").rows.find(r => r.id === "mlb_moneyline")!;
    expect(mlb.values.gap).toBe(Number((0.166759 - 0.151008).toFixed(6)));
    expect(mlb.values.relative_gap).toBe(Number(((0.166759 - 0.151008) / 0.151008).toFixed(6)));
    const direction = get("signed-calibration-direction").rows.find(r => r.id === "mlb-model_prob")!;
    expect(direction.values.mean_p).toBe(0.511328);
    expect(direction.values.mean_y).toBe(0.489738);
    expect(direction.values.signed_gap).toBe(-0.02159);
  });

  it("measures observed month shifts without treating unequal cohorts as zeros", () => {
    const soccer = get("observed-cohort-shift").rows.find(r => r.id === "soccer_intl")!;
    expect(soccer.values.model_shift).toBe(Number((0.3346 - 0.3273).toFixed(6)));
    expect(soccer.values.market_shift).toBe(Number((0.195 - 0.1955).toFixed(6)));
    expect(soccer.values.early_n).toBe(1213);
    expect(soccer.values.late_n).toBe(3052);
  });

  it("uses published cluster intervals and distinct-game support", () => {
    const width = get("cluster-interval-width").rows.find(r => r.id === "soccer_intl-model_prob")!;
    expect(width.values.widest_width).toBe(Number((0.3922 - -0.2935).toFixed(6)));
    expect(width.values.min_games).toBe(2);
    const support = get("calibration-support-concentration").rows.find(r => r.id === "soccer_intl-model_prob")!;
    expect(support.values.sparse_rows).toBe(4265);
    expect(support.values.n_rows).toBe(4265);
    expect(support.values.sparse_row_share).toBe(Number((4265 / 4265).toFixed(6)));
  });

  it("derives verdict diversity and friction from current family counts", () => {
    const mlbEntropy = get("verdict-mix-entropy").rows.find(r => r.id === "mlb")!;
    const counts = [32, 31, 8, 6, 1], n = 78;
    const expected = -counts.reduce((s, c) => s + (c / n) * Math.log2(c / n), 0);
    expect(mlbEntropy.values.entropy_bits).toBe(Number(expected.toFixed(6)));
    const mlbFriction = get("verdict-friction-share").rows.find(r => r.id === "mlb")!;
    expect(mlbFriction.values.not_testable_share).toBe(Number((8 / 78).toFixed(6)));
    expect(mlbFriction.values.retracted_share).toBe(Number((6 / 78).toFixed(6)));
  });

  it("keeps QA denominators separate and fails closed on nonfinite values", () => {
    const coverage = get("answer-evidence-coverage");
    expect(coverage.rows.find(r => r.id === "stress")?.values).toMatchObject({ covered: 316, eligible: 863, gap: 547 });
    expect(coverage.rows.find(r => r.id === "regression")?.values).toMatchObject({ covered: 87, eligible: 87, gap: 0 });
    for (const d of data) for (const r of d.rows) expect(Object.values(r.values).every(v => v === null || Number.isFinite(v))).toBe(true);
  });
});
