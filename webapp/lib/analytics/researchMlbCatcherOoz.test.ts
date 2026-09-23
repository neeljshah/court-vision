import { describe, expect, it } from "vitest";
import { buildMlbCatcherOozResearch } from "./researchMlbCatcherOoz";

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
  });

  it("orders catcher rows by strike rate", () => {
    const rows = buildMlbCatcherOozResearch({ catcher_ooz: { top: [catcher("Lower", 0.2, 700)], bottom: [catcher("Higher", 0.3, 600)] } })[0].rows;
    expect(rows.map(row => row.label)).toEqual(["Higher", "Lower"]);
  });

  it("keeps duplicate labels tied to their original indices through filtering and ranking", () => {
    const malformed = { name: "Filtered", ooz_strike_rate: 2, n_ooz_called: 1 };
    const rows = buildMlbCatcherOozResearch({ catcher_ooz: { bottom: [
      malformed,
      null,
      catcher("Carlos Perez", 0.2, 300),
      catcher("Carlos Perez", 0.4, 500),
    ] } })[0].rows;

    expect(rows.map(row => [row.label, row.values.out_of_zone_strike_rate, row.values.out_of_zone_called_pitches])).toEqual([
      ["Carlos Perez", 0.4, 500],
      ["Carlos Perez", 0.2, 300],
    ]);
    expect(rows.map(row => row.sourcePaths)).toEqual([
      ["catcher_ooz.bottom[3].name", "catcher_ooz.bottom[3].ooz_strike_rate", "catcher_ooz.bottom[3].n_ooz_called"],
      ["catcher_ooz.bottom[2].name", "catcher_ooz.bottom[2].ooz_strike_rate", "catcher_ooz.bottom[2].n_ooz_called"],
    ]);
  });

  it("returns no rows for missing or malformed catcher selections", () => {
    expect(buildMlbCatcherOozResearch({ catcher_ooz: { top: [catcher("Bad", 1.1, 600)] } })[0].rows).toEqual([]);
    expect(buildMlbCatcherOozResearch({})[0].rows).toEqual([]);
  });
});
