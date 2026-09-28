import { describe, expect, it } from "vitest";
import { buildMlbCatcherOozResearch, getMlbCatcherOozResearch } from "./researchMlbCatcherOoz";
import source from "../../public/data/showcase/mlb_descriptive_leaderboards.json";

const catcher = (name: string, rate: number, pitches: number) => ({ name, ooz_strike_rate: rate, n_ooz_called: pitches });

describe("MLB catcher out-of-zone research", () => {
  it("exposes selection sizes and source qualification without a complete-population claim", () => {
    const analysis = getMlbCatcherOozResearch()[0];
    expect(analysis.rows).toHaveLength(30);
    expect(analysis.rows.map(row => [row.label, row.values.out_of_zone_strike_rate, row.values.out_of_zone_called_pitches]))
      .toEqual([...source.catcher_ooz.top, ...source.catcher_ooz.bottom].map(row => [row.name, row.ooz_strike_rate, row.n_ooz_called]));
    expect(analysis.scope).toContain("30 displayed selection rows");
    for (const text of ["upper 15; lower 15", "source reports 113 qualifying catcher rows", "not a count of verified distinct people", "minimum: 500 out-of-zone pitches with Statcast type S or B"]) {
      expect(analysis.description).toContain(text);
      expect(analysis.scope).toContain(text);
    }
    expect(analysis.populationDefinition).toMatchObject({ status: "unpublished" });
    expect(analysis.populationDefinition?.reason).toContain("full qualifying distribution and catcher IDs are unavailable");
    expect(analysis.scope).toContain("2022-2023");
    expect(analysis.asOf).toBe("2026-07-05");
    expect(analysis.rows.every(row => row.values.out_of_zone_called_pitches! >= 500)).toBe(true);
  });

  it("preserves unknown and malformed qualification metadata without coercion", () => {
    for (const n_qualified of [undefined, null, "113", -1, 1.5, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1]) {
      const analysis = buildMlbCatcherOozResearch({ catcher_ooz: { n_qualified, floor: "n_ooz_called>=500", top: [catcher("A", 0.3, 600)] } })[0];
      expect(analysis.scope).toContain("qualifying-row count is not published or invalid");
      expect(analysis.scope).toContain("upper 1; lower not published");
      expect(analysis.rows).toHaveLength(1);
    }
    for (const floor of [undefined, null, 500, "500", "n_ooz_called>=0", "n_ooz_called>=-1", "n_ooz_called>=500.5", "n_ooz_called>=500 extra", "n_ooz_called>=9007199254740992"]) {
      const analysis = buildMlbCatcherOozResearch({ catcher_ooz: { floor, n_qualified: 113 } })[0];
      expect(analysis.scope).toContain("qualification minimum is not published or invalid");
      expect(analysis.scope).not.toContain("Source-reported minimum:");
    }
  });

  it("discloses conflicting counts and below-floor rows without dropping published evidence", () => {
    const analysis = buildMlbCatcherOozResearch({ catcher_ooz: {
      n_qualified: 1, floor: "n_ooz_called>=500",
      top: [catcher("A", 0.3, 499), catcher("B", 0.2, 500)], bottom: [],
    } })[0];
    expect(analysis.scope).toContain("qualifying-row count conflicts with its selection sizes");
    expect(analysis.scope).toContain("At least one displayed row is below this reported minimum");
    expect(analysis.rows.map(row => row.values.out_of_zone_called_pitches)).toEqual([499, 500]);
    const empty = buildMlbCatcherOozResearch({ catcher_ooz: { n_qualified: 0, top: [], bottom: [] } })[0];
    expect(empty.scope).toContain("upper 0; lower 0");
    expect(empty.scope).toContain("source reports 0 qualifying catcher rows");
  });

  it("builds published catcher measurements with source paths", () => {
    const analysis = buildMlbCatcherOozResearch({ catcher_ooz: { top: [catcher("A Catcher", 0.3, 600)] } })[0];
    expect(analysis).toMatchObject({ id: "mlb-catcher-out-of-zone-strike-rate", source: "mlb_descriptive_leaderboards" });
    expect(analysis.rows[0].values).toMatchObject({ out_of_zone_strike_rate: 0.3, out_of_zone_called_pitches: 600 });
    expect(analysis.rows[0].sourcePaths).toEqual([
      "catcher_ooz.top[0].name",
      "catcher_ooz.top[0].ooz_strike_rate",
      "catcher_ooz.top[0].n_ooz_called",
    ]);
    expect(analysis.fields).toContainEqual(expect.objectContaining({
      key: "out_of_zone_called_pitches",
      label: "Out-of-zone pitch support (type S/B)",
    }));
    expect(analysis.caveat).toContain("out-of-zone pitches with Statcast type S or B");
    expect(analysis.caveat).toContain("called, swung, or fouled strikes");
    expect(analysis.caveat).not.toContain("Repeated published names");
    expect(analysis.rows[0].note).toBe("Upper published selection.");
    expect(JSON.stringify(analysis)).not.toContain("Out-of-zone called pitches");
  });

  it("retains published selection order instead of manufacturing a combined ranking", () => {
    const rows = buildMlbCatcherOozResearch({ catcher_ooz: { top: [catcher("Lower", 0.2, 700)], bottom: [catcher("Higher", 0.3, 600)] } })[0].rows;
    expect(rows.map(row => row.label)).toEqual(["Lower", "Higher"]);
  });

  it("keeps duplicate labels tied to their original indices through filtering", () => {
    const malformed = { name: "Filtered", ooz_strike_rate: 2, n_ooz_called: 1 };
    const analysis = buildMlbCatcherOozResearch({ catcher_ooz: { bottom: [
      malformed,
      null,
      catcher("Carlos Perez", 0.2, 300),
      catcher("Carlos Perez", 0.4, 500),
    ] } })[0];
    const rows = analysis.rows;

    expect(rows.map(row => [row.label, row.values.out_of_zone_strike_rate, row.values.out_of_zone_called_pitches])).toEqual([
      ["Carlos Perez", 0.2, 300],
      ["Carlos Perez", 0.4, 500],
    ]);
    expect(rows.map(row => row.sourcePaths)).toEqual([
      ["catcher_ooz.bottom[2].name", "catcher_ooz.bottom[2].ooz_strike_rate", "catcher_ooz.bottom[2].n_ooz_called"],
      ["catcher_ooz.bottom[3].name", "catcher_ooz.bottom[3].ooz_strike_rate", "catcher_ooz.bottom[3].n_ooz_called"],
    ]);
    expect(rows.every(row => row.note?.includes("identity cannot be resolved"))).toBe(true);
    expect(analysis.caveat).toContain("cannot be assigned to distinct or identical people");
  });

  it("marks repeated names across upper and lower selections without changing either row", () => {
    const analysis = buildMlbCatcherOozResearch({ catcher_ooz: {
      top: [catcher("Shared Name", 0.4, 600), catcher("Unique Name", 0.3, 700)],
      bottom: [catcher("shared name", 0.2, 800)],
    } })[0];
    expect(analysis.rows.map(row => [row.label, row.values.out_of_zone_strike_rate, row.values.out_of_zone_called_pitches])).toEqual([
      ["Shared Name", 0.4, 600], ["Unique Name", 0.3, 700], ["shared name", 0.2, 800],
    ]);
    expect(analysis.rows[0].note).toContain("identity cannot be resolved");
    expect(analysis.rows[1].note).toBe("Upper published selection.");
    expect(analysis.rows[2].note).toContain("identity cannot be resolved");
    expect(analysis.rows[2].sourcePaths?.[0]).toBe("catcher_ooz.bottom[0].name");
  });

  it("discloses the two Carlos Perez rows in the committed public snapshot", () => {
    const analysis = getMlbCatcherOozResearch()[0];
    const repeated = analysis.rows.filter(row => row.label === "Carlos P\u00e9rez");
    expect(repeated.map(row => [row.values.out_of_zone_strike_rate, row.values.out_of_zone_called_pitches, row.sourcePaths?.[0]])).toEqual([
      [0.253, 2234, "catcher_ooz.bottom[2].name"],
      [0.239, 1277, "catcher_ooz.bottom[12].name"],
    ]);
    expect(repeated.every(row => row.note?.includes("source has no player IDs"))).toBe(true);
    expect(analysis.caveat).toContain("Repeated published names have no player IDs");
  });

  it("returns no rows for missing or malformed catcher selections", () => {
    expect(buildMlbCatcherOozResearch({ catcher_ooz: { top: [catcher("Bad", 1.1, 600)] } })[0].rows).toEqual([]);
    expect(buildMlbCatcherOozResearch({})[0].rows).toEqual([]);
  });
});
