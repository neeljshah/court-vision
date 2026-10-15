import { describe, expect, it } from "vitest";
import { buildMarketDisagreementResearch } from "./researchMarketDisagreement";
import published from "../../public/data/showcase/market_disagreement_profile.json";
import { buildLabCSV } from "../../components/analytics/lab/LabTable";

const row = (bucket: string, n = 40) => ({ bucket, n, model_brier: 0.2, market_brier: 0.18, model_closer_rate: 0.4 });

describe("market disagreement research", () => {
  it("preserves the published source date in analysis and CSV without inferring an observation window", () => {
    const analysis = buildMarketDisagreementResearch(published)[0];
    expect(analysis.asOf).toBe(published.as_of);
    expect(analysis.scope).toContain(`Published source as of ${published.as_of}.`);
    expect(analysis.scope).toContain("This date does not identify the observation window.");
    expect(analysis.rows).toHaveLength(8);
    expect(buildLabCSV(analysis, analysis.rows)).toContain(`"${published.as_of}"`);
  });

  it.each([undefined, null, "", "unknown", "2026-02-30", 20260916])("keeps unavailable source dates explicit (%s)", as_of => {
    const analysis = buildMarketDisagreementResearch({ as_of, sports: { mlb: [row("<.02")] } })[0];
    expect(analysis.asOf).toBeUndefined();
    expect(analysis.scope).toContain("Source as-of date not published.");
    expect(analysis.rows[0].values.scored_rows).toBe(40);
  });

  it("builds published Brier measurements with source paths", () => {
    const analysis = buildMarketDisagreementResearch({ sports: { mlb: [row("<.02")] } })[0];
    expect(analysis).toMatchObject({ id: "market-disagreement-brier-by-bucket", source: "market_disagreement_profile" });
    expect(analysis.rows[0].values).toMatchObject({ model_brier: 0.2, market_brier: 0.18, scored_rows: 40 });
    expect(analysis.rows[0].sourcePaths).toContain("sports.mlb[].market_brier");
    expect(analysis.bindings?.every(binding => binding.valueKey in analysis.rows[0].values)).toBe(true);
  });

  it("orders rows by sport and label", () => {
    const rows = buildMarketDisagreementResearch({ sports: { soccer_intl: [row(">=.10")], mlb: [row(".05-.10")] } })[0].rows;
    expect(rows.map(item => item.label)).toEqual(["International soccer | >=.10", "MLB | .05-.10"]);
  });

  it("returns no rows for missing or malformed buckets", () => {
    expect(buildMarketDisagreementResearch({ sports: { mlb: [{ ...row("<.02"), n: -1 }] } })[0].rows).toEqual([]);
    expect(buildMarketDisagreementResearch({})[0].rows).toEqual([]);
  });
});
