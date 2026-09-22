import { afterEach, describe, expect, it, vi } from "vitest";
import * as source from "./labHelpers";
import { multisportResearch } from "./researchMultisport";
import { outcomeBalance, safeDivide, supportRate, velocityShape } from "./researchMultisportHelpers";

const readSnapshot = source.snapshot;
afterEach(() => vi.restoreAllMocks());

describe("multisportResearch", () => {
  const analyses = multisportResearch();

  it("publishes nine populated, source-backed analyses with complete research metadata", () => {
    expect(analyses).toHaveLength(9);
    expect(new Set(analyses.map(a => a.id)).size).toBe(9);
    for (const analysis of analyses) {
      expect(analysis.rows.length).toBeGreaterThan(0);
      expect(analysis.fields.length).toBeGreaterThan(0);
      expect(analysis.formula).toBeTruthy();
      expect(analysis.interpretation).toBeTruthy();
      expect(analysis.references.every(r => r.url.startsWith("https://"))).toBe(true);
      expect(analysis.source).toMatch(/^(statcast_showcase|mlb_count_leverage|tennis_surface_transfer|soccer_home_advantage|soccer_form_stability)$/);
    }
    expect(analyses.filter(a => a.sport === "mlb")).toHaveLength(3);
    expect(analyses.filter(a => a.sport === "tennis")).toHaveLength(3);
    expect(analyses.filter(a => a.sport === "soccer")).toHaveLength(3);
  });

  it("recomputes representative MLB values from the public source operands", () => {
    const velocity = analyses.find(a => a.id === "mlb-velocity-shape")!;
    const fourSeam = velocity.rows.find(r => r.label === "FF")!;
    expect(fourSeam.values.spread).toBeCloseTo(fourSeam.values.p90! - fourSeam.values.p10!, 10);
    expect(fourSeam.values.asymmetry).toBeCloseTo(fourSeam.values.p90! + fourSeam.values.p10! - 2 * fourSeam.values.p50!, 10);

    const mix = analyses.find(a => a.id === "mlb-pitch-mix-concentration")!;
    const ff = mix.rows.find(r => r.label === "FF")!;
    expect(ff.values.share).toBeCloseTo(0.3178, 10);
    expect(ff.values.squared_share).toBeCloseTo(0.3178 ** 2, 10);
  });

  it("uses explicit denominators and keeps zero distinct from unavailable", () => {
    expect(safeDivide(0, 12)).toBe(0);
    expect(safeDivide(4, 0)).toBeNull();
    expect(safeDivide(null, 4)).toBeNull();
    expect(supportRate(0, 219)).toBe(0);
    expect(velocityShape({ p10: 80, p50: 85, p90: 95 })).toEqual({ spread: 15, asymmetry: 5, upperShare: 10 / 15 });
    expect(velocityShape({ p10: 80, p50: null, p90: 95 })).toEqual({ spread: null, asymmetry: null, upperShare: null });

    const support = analyses.find(a => a.id === "tennis-surface-support")!;
    const wta = support.rows.find(r => r.label === "WTA CAREER")!;
    expect(wta.values.clay_n).toBe(0);
    expect(wta.values.clay_support).toBe(0);
    const spread = analyses.find(a => a.id === "tennis-surface-spread")!;
    expect(spread.rows.find(r => r.label === "WTA CAREER")!.values.clay_width).toBeNull();
  });

  it("derives soccer outcome identities and preserves neutral directional cases", () => {
    expect(outcomeBalance({ home_win_rate: 0.5, draw_rate: 0, away_win_rate: 0.5 })).toEqual({ decisiveRate: 1, homeAwayMargin: 0, rateSum: 1 });
    expect(outcomeBalance({ home_win_rate: 0.5, draw_rate: null, away_win_rate: 0.5 }).decisiveRate).toBeNull();

    const venue = analyses.find(a => a.id === "soccer-venue-outcome-balance")!;
    const trueHome = venue.rows.find(r => r.label === "true home")!;
    expect(trueHome.values.decisiveRate).toBeCloseTo(1 - trueHome.values.draw_rate!, 10);
    expect(trueHome.values.homeAwayMargin).toBeCloseTo(trueHome.values.home_win_rate! - trueHome.values.away_win_rate!, 10);

    const alignment = analyses.find(a => a.id === "soccer-form-strength-alignment")!;
    expect(alignment.rows.find(r => r.label === "Albania")!.values.same_direction).toBeNull();
    expect(alignment.rows.find(r => r.label === "Argentina")!.values.same_direction).toBe(1);
    expect(alignment.scope).toContain("form is trailing-10 as of each team's corpus endpoint");
    expect(alignment.scope).toContain("strength is the 2026-06-28 snapshot");
    expect(alignment.caveat).toContain("unmatched as-of definitions");
    expect(alignment.caveat).toContain("not a synchronized snapshot");
    expect(alignment.scope).toContain("Shared teams in the published rankings: 153");
    expect(alignment.scope).toContain("form-only teams 26; strength-only teams 0");
    expect(alignment.rows).toHaveLength(153);
    expect(alignment.caveat).toContain("excluded, not scored as disagreements or zero values");
  });

  it.each([undefined, null, -1, 1.5, "26", Number.NaN, Number.MAX_SAFE_INTEGER + 1])(
    "keeps unavailable cohort counts distinct from zero (%s)", (invalid) => {
      vi.spyOn(source, "snapshot").mockImplementation(<T,>(id: string): T => {
        const data = readSnapshot<Record<string, unknown>>(id);
        if (id !== "soccer_form_stability") return data as T;
        return { ...data, concordance: {
          ...(data.concordance as Record<string, unknown>),
          n_overlap: invalid, n_form_only: invalid, n_strength_only: 0,
        } } as T;
      });
      const alignment = multisportResearch().find(a => a.id === "soccer-form-strength-alignment")!;
      expect(alignment.scope).toContain("Shared teams in the published rankings: unavailable");
      expect(alignment.scope).toContain("form-only teams unavailable; strength-only teams 0");
      expect(alignment.rows).toHaveLength(153);
      expect(alignment.rows.find(r => r.label === "Albania")!.values.same_direction).toBeNull();
    },
  );

  it("discloses that the MLB count-rate contrast uses separate denominators", () => {
    const count = analyses.find(a => a.id === "mlb-count-contrast")!;
    expect(count.caveat).toContain("separate non-null denominators (n_type and n_zone)");
    expect(count.formula).toContain("separately denominated");
    expect(count.interpretation).toContain("rather than a same-base event difference");
  });
});
