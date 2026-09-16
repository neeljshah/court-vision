import { describe, expect, it } from "vitest";
import { buildObservationDependence, median, shareAbovePointNine } from "./observationDependence";

const fixture = {
  sports: {
    mlb: {
      n_records: 12,
      n_series: 5,
      model: { n_games: 2, skipped: { low_n: 1, flat: 0 } },
      market: { n_games: 3, skipped: { low_n: 0, flat: 2 } },
      autocorr_values: { model: [0.2, 0.95], market: [0.1, 0.91, 0.99] },
    },
  },
};

describe("buildObservationDependence", () => {
  it("parses both published sides for a sport", () => {
    const sport = buildObservationDependence(fixture)[0];
    expect(sport.sides.map((side) => side.side)).toEqual(["model", "market"]);
    expect(sport.nRecords).toBe(12);
  });

  it("preserves unequal side lengths without pairing array positions", () => {
    const [model, market] = buildObservationDependence(fixture)[0].sides;
    expect(model.values).toEqual([0.2, 0.95]);
    expect(market.values).toEqual([0.1, 0.91, 0.99]);
    expect(model.nGames).toBe(2);
    expect(market.nGames).toBe(3);
  });

  it("computes median and share above 0.9 from the published arrays", () => {
    expect(median([0.1, 0.8, 0.9, 1])).toBe(0.85);
    expect(shareAbovePointNine([0.1, 0.91, 0.99])).toBeCloseTo(2 / 3);
    expect(buildObservationDependence(fixture)[0].sides[1]).toMatchObject({ median: 0.91, shareAbovePointNine: 2 / 3 });
  });

  it("handles a missing side without fabricating one", () => {
    const missing = { sports: { mlb: { ...fixture.sports.mlb, market: undefined } } };
    expect(buildObservationDependence(missing)[0].sides).toEqual([expect.objectContaining({ side: "model" })]);
  });
});
