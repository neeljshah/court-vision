import { describe, expect, it } from "vitest";
import scoreboard from "../../../public/data/showcase/cross_sport_scoreboard.json";
import { modelMinusMarket, DELTA_LEGEND } from "@/lib/scoreboardDelta";

// The home header says "model - market" and the legend says positive = model
// worse (lower Brier / CRPS is better). The artifact stores market - model, so
// every MARKET_SHARPER row must display positive and every MODEL_SHARPER row negative.
describe("home scoreboard delta sign", () => {
  it("negates the stored market-minus-model value and its interval", () => {
    expect(modelMinusMarket(-0.0084, [-0.016101811879082918, -0.0007999346168341686]))
      .toEqual({ delta: 0.0084, ci: [0.0008, 0.0161] });
  });

  it("shows MARKET_SHARPER rows as positive (model worse) and MODEL_SHARPER rows as negative", () => {
    const sharper = scoreboard.rows.filter((r) => r.verdict.includes("SHARPER"));
    expect(sharper.length).toBeGreaterThan(0);
    for (const r of sharper) {
      const { delta, ci } = modelMinusMarket(r.paired_delta_mean, r.paired_delta_95ci as [number, number]);
      if (r.verdict.startsWith("MARKET_SHARPER")) expect(delta).toBeGreaterThan(0);
      if (r.verdict.startsWith("MODEL_SHARPER")) expect(delta).toBeLessThan(0);
      expect(ci[0]).toBeLessThanOrEqual(ci[1]);
    }
  });

  it("states the direction in the legend", () => {
    expect(DELTA_LEGEND).toBe("lower Brier is better; delta = model minus market; positive = model worse");
  });
});
