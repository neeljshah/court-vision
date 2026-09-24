import { describe, expect, it } from "vitest";
import { buildMlbCatcherOozResearch, getMlbCatcherOozResearch } from "./researchMlbCatcherOoz";

const catcher = (name: string, rate: number, pitches: number) => ({ name, ooz_strike_rate: rate, n_ooz_called: pitches });

describe("MLB catcher out-of-zone research", () => {
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

  it("orders catcher rows by strike rate", () => {
    const rows = buildMlbCatcherOozResearch({ catcher_ooz: { top: [catcher("Lower", 0.2, 700)], bottom: [catcher("Higher", 0.3, 600)] } })[0].rows;
    expect(rows.map(row => row.label)).toEqual(["Higher", "Lower"]);
  });

  it("keeps duplicate labels tied to their original indices through filtering and ranking", () => {
    const malformed = { name: "Filtered", ooz_strike_rate: 2, n_ooz_called: 1 };
    const analysis = buildMlbCatcherOozResearch({ catcher_ooz: { bottom: [
      malformed,
      null,
      catcher("Carlos Perez", 0.2, 300),
      catcher("Carlos Perez", 0.4, 500),
    ] } })[0];
    const rows = analysis.rows;

    expect(rows.map(row => [row.label, row.values.out_of_zone_strike_rate, row.values.out_of_zone_called_pitches])).toEqual([
      ["Carlos Perez", 0.4, 500],
      ["Carlos Perez", 0.2, 300],
    ]);
    expect(rows.map(row => row.sourcePaths)).toEqual([
      ["catcher_ooz.bottom[3].name", "catcher_ooz.bottom[3].ooz_strike_rate", "catcher_ooz.bottom[3].n_ooz_called"],
      ["catcher_ooz.bottom[2].name", "catcher_ooz.bottom[2].ooz_strike_rate", "catcher_ooz.bottom[2].n_ooz_called"],
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
