import { describe, expect, it } from "vitest";
import { buildMicroAbsorptionResearch } from "./researchMicroAbsorption";
import published from "../../public/data/showcase/micro_absorption.json";
import { buildLabCSV } from "../../components/analytics/lab/LabTable";

const source = (mean = 0.02) => ({ buckets_minutes: [{ label: "6h+" }], sports: { mlb: { status: "ok", n_series_used: 4, move_by_bucket: { "6h+": { n: 20, mean_abs_move: mean } } } } });

describe("time-to-close movement research", () => {
  it("preserves the overall file span and each sport's own window in row context and CSV", () => {
    const analysis = buildMicroAbsorptionResearch(published)[0];
    expect(analysis.asOf).toBe("2026-07-25");
    expect(analysis.scope).toContain("Source file window: 2026-06-18 to 2026-07-17.");
    expect(analysis.caveat).toContain("consumed daily files, not event-date coverage");
    expect(analysis.rows).toHaveLength(21);
    for (const [sport, record] of Object.entries(published.sports)) {
      const sportRows = analysis.rows.filter(row => row.sourcePaths?.includes(`sports.${sport}.n_series_used`));
      for (const row of sportRows) {
        const window = `${record.observation_window.start} to ${record.observation_window.end} (consumed daily files)`;
        expect(Object.values(row.windows || {})).toEqual([window, window, window]);
        expect(row.sourcePaths).toContain(`sports.${sport}.observation_window.start`);
        expect(row.note).toContain("sport-wide series across all time buckets");
      }
    }
    const tennis = analysis.rows.find(row => row.label === "TENNIS | 0-1h")!;
    expect(tennis.values).toEqual({ mean_absolute_devigged_probability_movement: 0.00019, move_pairs: 47072, series_used: 2510 });
    expect(tennis.note).toContain("Sport file window: 2026-07-03 to 2026-07-17.");
    const csv = buildLabCSV(analysis, [tennis]);
    expect(csv).toContain("2026-07-03 to 2026-07-17 (consumed daily files)");
    expect(csv).toContain('"2026-07-25"');
  });

  it.each([undefined, null, {}, "2026-07", { start: "2026-02-30", end: "2026-07-17" },
    { start: "2026-07-18", end: "2026-07-17" }, { start: 20260703, end: "2026-07-17" },
  ])("does not replace a missing or invalid sport window with the overall span (%j)", observation_window => {
    const fixture = source();
    const analysis = buildMicroAbsorptionResearch({ ...fixture,
      observation_window: { start: "2026-06-18", end: "2026-07-17" },
      sports: { mlb: { ...fixture.sports.mlb, observation_window } },
    })[0];
    expect(analysis.scope).toContain("Source file window: 2026-06-18 to 2026-07-17.");
    expect(analysis.rows[0].windows).toBeUndefined();
    expect(analysis.rows[0].note).toContain("Sport file window not published.");
    expect(analysis.rows[0].values.move_pairs).toBe(20);
  });

  it("keeps a published sport window when the overall window is absent", () => {
    const fixture = source();
    const analysis = buildMicroAbsorptionResearch({ ...fixture,
      sports: { mlb: { ...fixture.sports.mlb, observation_window: { start: "2026-07-03", end: "2026-07-17" } } },
    })[0];
    expect(analysis.scope).toContain("Source file window not published.");
    expect(analysis.rows[0].windows?.move_pairs).toBe("2026-07-03 to 2026-07-17 (consumed daily files)");
  });

  it("builds published movement measurements with source paths", () => {
    const analysis = buildMicroAbsorptionResearch(source())[0];
    expect(analysis).toMatchObject({ id: "devigged-movement-by-time-to-close", source: "micro_absorption" });
    expect(analysis.rows[0].values).toMatchObject({ mean_absolute_devigged_probability_movement: 0.02, move_pairs: 20, series_used: 4 });
    expect(analysis.rows[0].sourcePaths).toContain("sports.mlb.move_by_bucket.6h+.mean_abs_move");
  });

  it("orders rows by sport and bucket label", () => {
    const rows = buildMicroAbsorptionResearch({ buckets_minutes: [{ label: "0-1h" }, { label: "6h+" }], sports: { wnba: { status: "ok", n_series_used: 2, move_by_bucket: { "0-1h": { n: 2, mean_abs_move: 0.1 }, "6h+": { n: 3, mean_abs_move: 0.2 } } }, mlb: { status: "ok", n_series_used: 1, move_by_bucket: { "0-1h": { n: 4, mean_abs_move: 0.3 }, "6h+": { n: 5, mean_abs_move: 0.4 } } } } })[0].rows;
    expect(rows.map(row => row.label)).toEqual(["MLB | 0-1h", "MLB | 6h+", "WNBA | 0-1h", "WNBA | 6h+"]);
  });

  it("returns no rows for missing or malformed buckets", () => {
    expect(buildMicroAbsorptionResearch({ buckets_minutes: [{ label: "6h+" }], sports: { mlb: { status: "ok", n_series_used: 1, move_by_bucket: { "6h+": { n: 2, mean_abs_move: -0.1 } } } } })[0].rows).toEqual([]);
    expect(buildMicroAbsorptionResearch({})[0].rows).toEqual([]);
  });

  it("does not attribute movement timing to a particular cause", () => {
    const analysis = buildMicroAbsorptionResearch(source())[0];
    const prose = [analysis.description, analysis.caveat, analysis.interpretation].join(" ");
    expect(prose).not.toMatch(/lineup|scratch|sharp money|information actually arrives/i);
    expect(analysis.interpretation).toContain("does not identify its cause");
  });
});
