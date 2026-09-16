import { describe, expect, it } from "vitest";
import { loadCountContext } from "./countContext.server";
import { buildCountContext } from "./countContext";

const fixture = {
  as_of: "2026-07-25", by_leverage_class: [{ class: "behind", definition: "published", overlapping: false, n: 10, pitch_type_n: 9,
    pitch_mix_top: [{ pitch_type: "FF", n: 4, pct: 44.44 }], outcome_proxies: { n_type: 10, strike_rate_type_S: 0.2, ball_rate: 0.3, inplay_rate_type_X: 0.5, n_zone: 9, in_zone_rate: 0.6 } }],
};

describe("count context data", () => {
  it("preserves independently published denominators and unscaled mix percentages", () => {
    const row = buildCountContext(fixture).classes[0];
    expect(row).toMatchObject({ n: 10, pitchTypeN: 9, pitchMix: [{ pitchType: "FF", n: 4, pct: 44.44 }], outcomes: { nType: 10, nZone: 9 } });
    expect(row.remainderPct).toBe(55.56);
  });

  it("loads all five count classes, their overlap flags, and the published denominators", () => {
    const data = loadCountContext();
    expect(data.classes.map(item => item.id)).toEqual(["behind", "even", "ahead", "two_strike", "three_ball"]);
    expect(data.classes.map(item => item.n)).toEqual([183042, 305712, 204283, 207101, 56806]);
    expect(data.classes.map(item => item.pitchTypeN)).toEqual([181462, 304924, 204107, 206876, 56216]);
    expect(data.classes.map(item => item.outcomes.nType)).toEqual([183042, 305712, 204283, 207101, 56806]);
    expect(data.classes.map(item => item.outcomes.nZone)).toEqual([181462, 304924, 204107, 206876, 56216]);
    expect(data.classes.map(item => item.overlapping)).toEqual([false, false, false, true, true]);
    expect(data.classes.map(item => item.pitchMix[0]?.pct)).toEqual([35.25, 31.3, 29.8, 31.98, 41.93]);
    expect(data.classes.map(item => item.remainderPct)).toEqual([0.47, 0.47, 0.43, 0.37, 0.34]);
  });
});
