import { describe, expect, it } from "vitest";
import { buildMarketDisagreementResearch } from "./researchMarketDisagreement";

const row = (bucket: string, n = 40) => ({ bucket, n, model_brier: 0.2, market_brier: 0.18, model_closer_rate: 0.4 });

describe("market disagreement research", () => {
  it("builds published Brier measurements with source paths", () => {
    const analysis = buildMarketDisagreementResearch({ sports: { mlb: [row("<.02")] } })[0];
    expect(analysis).toMatchObject({ id: "market-disagreement-brier-by-bucket", source: "market_disagreement_profile" });
    expect(analysis.rows[0].values).toMatchObject({ model_brier: 0.2, market_brier: 0.18, scored_rows: 40 });
    expect(analysis.rows[0].sourcePaths).toContain("sports.mlb[].market_brier");
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
