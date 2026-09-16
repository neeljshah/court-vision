import { describe, expect, it } from "vitest";
import { entrySlugs, formatMetric, formatPercentile, metricUnit, normalizeComparisonPack } from "./comparisonData";

describe("comparison data normalization", () => {
  const manifest = { entries: [
    { entity: "Alpha One", card_path: "docs/a/shared.png", key_numbers: { career_pts_per36: 12, player_id: 1, career_fg_pct: null }, as_of: "2026-04-12", floors: "minutes>=800", status: "partial" },
    { entity: "Beta Two", card_path: "docs/b/shared.png", key_numbers: { career_pts_per36: 16, player_id: 2, career_fg_pct: 41.5 } },
  ] };
  const percentiles = { packs: { demo: { n_in_pack: 2, fields: { career_pts_per36: { n_ranked: 2 }, career_fg_pct: { n_ranked: 1 } }, entities: { shared: { career_pts_per36: 25 }, beta_two: { career_pts_per36: 75, career_fg_pct: 50 } } } } };
  const comparables = {
    method: "Cosine similarity on z-scored published fields.",
    skipped_packs: [{ pack: "tennis", reason: "too few common fields", n_entities: 278, n_common_fields: 0 }],
    packs: { demo: {
      fields_used: ["career_pts_per36", "career_games"],
      dropped_zero_variance: ["seasons_covered"],
      entities: { shared: { similar: [{ slug: "beta_two", name: "Beta Two", score: 0.75 }], antipode: { slug: "beta_two", name: "Beta Two", score: -0.75 } } },
    } },
  };

  it("preserves the entity-route slug collision rule and published ranks", () => {
    expect(entrySlugs(manifest.entries).map((item) => item.slug)).toEqual(["shared", "beta_two"]);
    const pack = normalizeComparisonPack("demo", manifest, percentiles, comparables);
    expect(pack.metricKeys).toEqual(["career_pts_per36", "career_fg_pct"]);
    expect(pack.nRankedByMetric).toEqual({ career_pts_per36: 2, career_fg_pct: 1 });
    expect(pack.suggestedPair).toEqual(["shared", "beta_two"]);
    expect(pack.comparableContext).toMatchObject({ method: "Cosine similarity on z-scored published fields.", fieldsUsed: ["career_pts_per36", "career_games"], droppedZeroVariance: ["seasons_covered"] });
    expect(pack.antipodeByEntity?.shared).toEqual({ slug: "beta_two", name: "Beta Two", score: -0.75 });
    expect(pack.entities[0].percentiles.career_pts_per36).toBe(25);
    expect(pack.entities[0]).toMatchObject({ sourceEntity: "Alpha One", asOf: "2026-04-12", floors: "minutes>=800", status: "partial" });
  });

  it("preserves the published skipped-pack reason and common field count", () => {
    const pack = normalizeComparisonPack("tennis", { entries: [] }, { packs: { tennis: { n_in_pack: 278 } } }, comparables);
    expect(pack.comparableContext?.skipped).toEqual({ reason: "too few common fields", nEntities: 278, nCommonFields: 0 });
  });

  it("preserves only published finite nonnegative integer cohort sizes", () => {
    const fields = {
      zero: { n_ranked: 0 }, smaller: { n_ranked: 1 }, missing: {},
      fractional: { n_ranked: 1.5 }, negative: { n_ranked: -1 }, infinite: { n_ranked: Infinity },
    };
    const pack = normalizeComparisonPack("demo", manifest, { packs: { demo: { n_in_pack: 2, fields } } }, {});
    expect(pack.metricKeys).toEqual(Object.keys(fields));
    expect(pack.nRankedByMetric).toEqual({ zero: 0, smaller: 1 });
  });

  it("keeps missing values missing and labels units without inventing a zero", () => {
    expect(formatMetric(null, "career_fg_pct")).toBe("Not reported");
    expect(formatMetric(12, "career_fg_pct")).toBe("12.0%");
    expect(formatMetric(0.6906, "hard_wr_career")).toBe("69.06%");
    expect(formatMetric(0.1351, "clean_sheet_rate_season")).toBe("13.51%");
    expect(formatMetric(0.06, "pct_of_all_pitches")).toBe("0.06%");
    expect(formatMetric(0.056, "clay_minus_hard_career")).toBe("5.6 pp");
    expect(formatMetric(-0.043, "grass_adapt_career")).toBe("-4.3 pp");
    expect(formatMetric(-0, "clay_minus_hard_recent")).toBe("0 pp");
    expect(formatMetric(0.00000001, "hard_wr_career")).toBe("<0.001%");
    expect(formatMetric(-0.00000001, "grass_adapt_recent")).toBe(">-0.01 pp");
    expect(formatMetric(0.0000001, "estimated_woba")).toBe("<0.001");
    expect(metricUnit("clay_minus_hard_career")).toBe("percentage points");
    expect(metricUnit("grass_adapt_recent")).toBe("percentage points");
    expect(metricUnit("career_pts_per36")).toBe("per 36");
    expect(formatPercentile(undefined)).toBe("Not ranked");
    expect(formatPercentile(32)).toBe("32nd percentile");
    expect(formatPercentile(11)).toBe("11th percentile");
    expect(formatPercentile(21)).toBe("21st percentile");
  });
});
