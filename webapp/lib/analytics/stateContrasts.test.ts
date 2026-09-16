import { describe, expect, it } from "vitest";
import { deltaPercentagePoints, buildStateContrasts, contrastsForPair } from "./stateContrasts";
import { loadStateContrasts } from "./stateContrasts.server";

describe("state contrast data", () => {
  it("parses the 40 published MLB and 80 published soccer rows", () => {
    const sports = loadStateContrasts();
    expect(sports.find(sport => sport.sport === "mlb")?.contrasts).toHaveLength(40);
    expect(sports.find(sport => sport.sport === "soccer_intl")?.contrasts).toHaveLength(80);
  });

  it("preserves signed deltas and rounds computed percentage points to six decimals", () => {
    const parsed = buildStateContrasts({ sports: { sample: { transitions: [{
      from: { time: "early", prob: ".2-.4", mean_y: 0.12345678, n: 12 },
      to: { time: "mid", prob: ".4-.6", mean_y: 0.87654321, n: 13 },
      winprob_delta: -0.33333339,
      min_support_n: 12,
    }] } } });
    expect(parsed[0].contrasts[0].winprobDelta).toBe(-0.333333);
    expect(deltaPercentagePoints(parsed[0].contrasts[0].winprobDelta)).toBe(-33.3333);
  });

  it("retains both published populations and the minimum support", () => {
    const contrast = loadStateContrasts().find(sport => sport.sport === "mlb")?.contrasts[0];
    expect(contrast).toMatchObject({
      from: { time: "early(inn1-3)", probabilityBand: ".2-.4", meanOutcomeFrequency: 0.3596, n: 2458 },
      to: { time: "mid(inn4-6)", probabilityBand: "0-.2", meanOutcomeFrequency: 0.2063, n: 2079 },
      minSupportN: 2079,
    });
  });

  it("returns no rows for a missing sport", () => {
    const sports = loadStateContrasts();
    expect(contrastsForPair(sports, "missing", "early__mid")).toEqual([]);
  });
});
