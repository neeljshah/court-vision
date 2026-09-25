import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
// @ts-expect-error -- the executable copy scanner is dependency-free ESM.
import { PROHIBITED_TOKEN_RE } from "../../scripts/check-analytics-copy.mjs";
import { getTimingModuleEvidence } from "./timingModuleEvidence";

const artifact = (id: string): Record<string, unknown> => JSON.parse(readFileSync(
  join(process.cwd(), "public", "data", "showcase", `${id}.json`), "utf8",
));
const strings = (value: unknown): string[] => typeof value === "string" ? [value]
  : Array.isArray(value) ? value.flatMap(strings)
  : value && typeof value === "object" ? Object.values(value).flatMap(strings) : [];

describe("timing module evidence", () => {
  it("matches each published LCF sport row and its individual denominator", () => {
    const source = artifact("novel_live_clock_fraction");
    const evidence = getTimingModuleEvidence("novel_live_clock_fraction", source)!;
    const results = source.results as Array<Record<string, unknown>>;
    expect(evidence.snapshotDate).toBe(source.as_of);
    expect(evidence.askQuestion).toBe("What is the Live-Clock Fraction?");
    expect(evidence.tables.map(table => table.title)).toEqual(["MLB", "International soccer"]);
    expect(evidence.tables.map(table => table.rows.length)).toEqual([1, 1]);
    for (const result of results) {
      const row = evidence.tables.flatMap(table => table.rows).find(item => item.id === result.sport)!;
      expect(row).toMatchObject({
        live_clock_fraction: result.live_clock_fraction,
        threshold: result.near_median_threshold,
        unit: result.unit,
        clock_field: result.clock_field,
        n_games_decided: result.n_games_decided,
        n_games_total: result.n_games_total,
        decided_frac_of_games: result.decided_frac_of_games,
      });
      expect(evidence.receipts.some(receipt => receipt.value ===
        `${result.n_games_decided} of ${result.n_games_total} games with usable score paths`)).toBe(true);
    }
    expect(evidence.method).toContain("last reversion");
    expect(evidence.method).toContain("observation window is not published");
    expect(evidence.caveat).toContain("not buildable");
    expect(evidence.missing).toEqual([]);
  });

  it("keeps every MFP checkpoint in separate sport tables", () => {
    const source = artifact("novel_market_foresight_premium");
    const evidence = getTimingModuleEvidence("novel_market_foresight_premium", source)!;
    const results = source.results as Record<string, { checkpoints: Array<Record<string, unknown>> }>;
    expect(evidence.tables.map(table => table.id)).toEqual(["mfp-mlb", "mfp-soccer_intl"]);
    expect(evidence.tables.map(table => table.title)).toEqual(["MLB", "International soccer"]);
    expect(evidence.tables.map(table => table.rows.length)).toEqual([10, 19]);
    expect(evidence.askQuestion).toBe("What is the Market Foresight Premium?");
    expect(evidence.snapshotDate).toBe(source.as_of);
    for (const [index, sport] of ["mlb", "soccer_intl"].entries()) {
      const points = results[sport].checkpoints;
      const rows = evidence.tables[index].rows;
      for (const [position, point] of points.entries()) {
        expect(rows[position]).toMatchObject({
          checkpoint: point.checkpoint, mfp: point.mfp, market_skill: point.market_skill,
          model_skill: point.model_skill, entropy_market_bits: point.entropy_market_bits,
          n: point.n, entropy_floored: point.entropy_floored ? "Yes" : "No",
        });
      }
      expect(evidence.receipts[index].value).toBe(String(points.at(-1)!.n));
    }
    expect(evidence.denominator).toContain("unique game counts unavailable");
    expect(evidence.method).toContain("observation window is not published");
    expect(evidence.missing).toEqual([]);
  });

  it("responds to changed source values instead of retaining published figures", () => {
    const lcf = artifact("novel_live_clock_fraction");
    (lcf.results as Array<Record<string, unknown>>)[0] = {
      ...(lcf.results as Array<Record<string, unknown>>)[0],
      live_clock_fraction: 0.4321, n_games_decided: 7, n_games_total: 41,
    };
    lcf.as_of = "2025-11-09";
    const changedLcf = getTimingModuleEvidence("novel_live_clock_fraction", lcf)!;
    expect(changedLcf.tables[0].rows[0]).toMatchObject({ live_clock_fraction: 0.4321, n_games_decided: 7, n_games_total: 41 });
    expect(changedLcf.receipts[0].value).toBe("7 of 41 games with usable score paths");
    expect(changedLcf.snapshotDate).toBe("2025-11-09");

    const mfp = artifact("novel_market_foresight_premium");
    const first = (mfp.results as Record<string, { checkpoints: Array<Record<string, unknown>> }>).mlb.checkpoints[0];
    first.mfp = 0.4321;
    first.n = 41;
    first.entropy_floored = true;
    mfp.entropy_floor_bits = 0.25;
    const changedMfp = getTimingModuleEvidence("novel_market_foresight_premium", mfp)!;
    expect(changedMfp.tables[0].rows[0]).toMatchObject({ mfp: 0.4321, n: 41, entropy_floored: "Yes" });
    expect(changedMfp.method).toContain("0.25-bit floor");
  });

  it("uses null and explicit unavailable labels for invalid or missing cells", () => {
    const lcf = getTimingModuleEvidence("novel_live_clock_fraction", {
      as_of: "2026-02-30",
      results: [{ sport: "mlb", live_clock_fraction: NaN, near_median_threshold: Infinity,
        n_games_decided: -1, n_games_total: "9", decided_frac_of_games: null }],
    })!;
    expect(lcf.snapshotDate).toBeNull();
    expect(lcf.tables[0].rows[0]).toMatchObject({
      live_clock_fraction: null, threshold: null, unit: null, clock_field: null,
      n_games_decided: null, n_games_total: null, decided_frac_of_games: null,
    });
    expect(lcf.receipts[0].value).toBe("unavailable of unavailable games with usable score paths");
    expect(lcf.missing).toContain("International soccer source row");
    expect(lcf.tables[1].rows).toEqual([]);

    const mfp = getTimingModuleEvidence("novel_market_foresight_premium", {
      as_of: "invalid", results: { mlb: { checkpoints: [{ checkpoint: "1", mfp: Infinity,
        market_skill: NaN, model_skill: null, entropy_market_bits: "0.5", n: 0.5 }] } },
    })!;
    expect(mfp.snapshotDate).toBeNull();
    expect(mfp.tables[0].rows[0]).toMatchObject({
      mfp: null, market_skill: null, model_skill: null, entropy_market_bits: null,
      n: null, entropy_floored: null,
    });
    expect(mfp.tables[1].rows).toEqual([]);
    expect(mfp.receipts.map(receipt => receipt.value)).toEqual(["unavailable", "unavailable"]);
    expect(mfp.missing).toContain("International soccer checkpoint rows");
  });

  it("rejects out-of-range fractions and inconsistent LCF denominators", () => {
    const evidence = getTimingModuleEvidence("novel_live_clock_fraction", {
      results: [{ sport: "mlb", unit: "runs", clock_field: "inning", near_median_threshold: -3,
        live_clock_fraction: 1.4, decided_frac_of_games: -0.1,
        n_games_decided: 12, n_games_total: 5 }],
    })!;
    expect(evidence.tables[0].rows[0]).toMatchObject({
      live_clock_fraction: null, threshold: null, n_games_decided: null,
      n_games_total: 5, decided_frac_of_games: null,
    });
    expect(evidence.receipts[0].value).toBe("unavailable of 5 games with usable score paths");
    expect(evidence.missing).toContain("MLB decided games exceed usable score paths");
    expect(evidence.missing).toContain("MLB live-clock fraction");
  });

  it("returns null for unsupported modules", () => {
    expect(getTimingModuleEvidence("other", {})).toBeNull();
  });

  it("keeps every rendered helper string clear of prohibited copy tokens", () => {
    for (const id of ["novel_live_clock_fraction", "novel_market_foresight_premium"]) {
      for (const source of [artifact(id), {}]) {
        const evidence = getTimingModuleEvidence(id, source);
        expect(strings(evidence).filter(value => PROHIBITED_TOKEN_RE.test(value))).toEqual([]);
      }
    }
  });
});
