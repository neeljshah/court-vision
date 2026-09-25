import { describe, expect, it } from "vitest";
// @ts-expect-error -- the executable copy scanner is dependency-free ESM.
import { PROHIBITED_TOKEN_RE } from "../../scripts/check-analytics-copy.mjs";
import { labComparisonPolicy } from "./labComparisonPolicy";
import { snapshot } from "./labHelpers";
import { buildMarketForesightLabDataset, getMarketForesightLabDataset } from "./labMarketForesight";
import { novelDatasets } from "./labNovel";

const checkpoint = (overrides: Record<string, unknown> = {}) => ({
  checkpoint: "1", n: 3589, market_skill: 0.0333, model_skill: -0.0154,
  entropy_market_bits: 0.9553, entropy_floored: false, mfp: 0.051, ...overrides,
});
const source = (point: unknown = checkpoint(), as_of: unknown = "2026-09-17", floor: unknown = 0.15) => ({
  as_of, entropy_floor_bits: floor, results: { mlb: { checkpoints: [point] } },
});

describe("market-foresight lab dataset", () => {
  it("preserves every published row, identifier, label and raw measurement", () => {
    const artifact = snapshot<{ results: Record<string, { checkpoints: ReturnType<typeof checkpoint>[] }> }>("novel_market_foresight_premium");
    const dataset = getMarketForesightLabDataset();
    expect(dataset.rows).toHaveLength(29);
    expect(dataset.fields.map(field => field.key)).toEqual([
      "mfp", "market_skill", "model_skill", "entropy_market_bits", "n", "checkpoint",
    ]);
    for (const [sport, result] of Object.entries(artifact.results)) {
      const group = sport === "mlb" ? "MLB" : "INTERNATIONAL SOCCER";
      for (const [index, raw] of result.checkpoints.entries()) {
        const row = dataset.rows.find(item => item.id === `${group}-${index}`)!;
        expect(row).toBeDefined();
        expect(row.label).toBe(`${group} / ${raw.checkpoint}`);
        expect(row.group).toBe(group);
        expect(row.values).toEqual({
          mfp: raw.mfp, market_skill: raw.market_skill, model_skill: raw.model_skill,
          entropy_market_bits: raw.entropy_market_bits, n: raw.n,
          checkpoint: Number(raw.checkpoint),
        });
        expect(row.note).toContain(`results.${sport}.checkpoints[${index}]`);
        expect(row.note).toContain("unique game count unavailable");
        expect(row.note).toContain("Entropy floored: No");
      }
    }
    expect(new Set(dataset.rows.map(row => row.id)).size).toBe(29);
    expect(novelDatasets().find(item => item.id === "market-foresight")).toEqual(dataset);
  });

  it("keeps sport clock cohorts separate without inventing dates or populations", () => {
    const dataset = getMarketForesightLabDataset();
    const mlb = dataset.rows.filter(row => row.group === "MLB");
    const soccer = dataset.rows.filter(row => row.group === "INTERNATIONAL SOCCER");
    expect([mlb.length, soccer.length]).toEqual([10, 19]);
    expect(mlb.every(row => row.definition?.clockField === "inning")).toBe(true);
    expect(soccer.every(row => row.definition?.clockField === "minute (5-minute bucket)")).toBe(true);
    expect(dataset.rows.every(row => row.definition?.observationWindow === undefined && row.definition?.population === undefined)).toBe(true);
    expect(labComparisonPolicy(dataset.rows).compatibility).toBe("incompatible");
    expect(dataset.scope).toContain("MLB inning checkpoints 1 to 10");
    expect(dataset.scope).toContain("INTERNATIONAL SOCCER minute (5-minute bucket) checkpoints 0 to 90+");
    expect(dataset.scope).toContain("Artifact date: 2026-09-17; observation window unavailable");
    expect(dataset.scope).toContain("Entropy floor: 0.15 bits");
    expect(dataset.caveat).toContain("0.15-bit entropy floor");
    expect(soccer.at(-1)?.note).toContain("90+ includes minute 90 and later");
    expect(dataset.fields.find(field => field.key === "market_skill")?.label).toBe("Closing reference skill vs. naive");
    expect(dataset.fields.find(field => field.key === "model_skill")?.label).toBe("State-only model skill vs. naive");
    expect(dataset.fields.find(field => field.key === "entropy_market_bits")?.label).toBe("Reference entropy (bits)");
  });

  it("validates source date and floor without inventing missing metadata", () => {
    const changed = buildMarketForesightLabDataset(source(checkpoint(), "2025-11-09", 0.2));
    expect(changed.scope).toContain("Artifact date: 2025-11-09");
    expect(changed.scope).toContain("Entropy floor: 0.2 bits");
    const missing = buildMarketForesightLabDataset(source(checkpoint(), "2026-02-30", null));
    expect(missing.scope).toContain("Artifact date: unavailable; observation window unavailable");
    expect(missing.scope).toContain("Entropy floor: unavailable");
    expect(missing.caveat).toContain("does not provide a valid entropy floor");
    expect(missing.rows[0].definition).not.toHaveProperty("observationWindow");
  });

  it("keeps malformed measurements null and validates counts and checkpoint strings", () => {
    const malformed = buildMarketForesightLabDataset(source(checkpoint({
      checkpoint: " 1 ", n: -1, mfp: "0.051", market_skill: Infinity,
      model_skill: NaN, entropy_market_bits: null, entropy_floored: null,
    })));
    expect(malformed.rows[0].values).toEqual({
      mfp: null, market_skill: null, model_skill: null,
      entropy_market_bits: null, n: null, checkpoint: null,
    });
    expect(malformed.rows[0].note).toContain("Entropy floored: Unavailable");
    for (const invalid of [null, -1, 0.5, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1, "1"]) {
      expect(buildMarketForesightLabDataset(source(checkpoint({ n: invalid }))).rows[0].values.n).toBeNull();
    }
    for (const invalid of [null, "", " 1", "1 ", "1e2", "0x10", "-1", NaN, Infinity]) {
      expect(buildMarketForesightLabDataset(source(checkpoint({ checkpoint: invalid }))).rows[0].values.checkpoint).toBeNull();
    }
    const genuineZero = buildMarketForesightLabDataset(source(checkpoint({ checkpoint: "0", n: 0, mfp: 0, entropy_floored: true })));
    expect(genuineZero.rows[0].values).toMatchObject({ checkpoint: 0, n: 0, mfp: 0 });
    expect(genuineZero.rows[0].note).toContain("Entropy floored: Yes");
    expect(buildMarketForesightLabDataset(source(checkpoint({ entropy_market_bits: -0.2 }))).rows[0].values.entropy_market_bits).toBeNull();
  });

  it("rejects malformed required result structure", () => {
    expect(() => buildMarketForesightLabDataset({})).toThrow("novel_market_foresight_premium.results must be an object");
    expect(() => buildMarketForesightLabDataset({ results: { mlb: {} } })).toThrow("novel_market_foresight_premium.results.mlb.checkpoints must be an array");
    expect(() => buildMarketForesightLabDataset(source(null))).toThrow("novel_market_foresight_premium.results.mlb.checkpoints[0] must be an object");
  });

  it("passes the shared public-copy token rule for every adapter string", () => {
    const strings = (value: unknown): string[] => typeof value === "string" ? [value]
      : Array.isArray(value) ? value.flatMap(strings)
      : value && typeof value === "object" ? Object.values(value).flatMap(strings) : [];
    for (const value of strings(getMarketForesightLabDataset())) {
      expect(PROHIBITED_TOKEN_RE.test(value), value).toBe(false);
    }
  });
});
