import { describe, expect, it } from "vitest";
import scoreboard from "@/public/data/showcase/fwd_claim_scoreboard.json";
import { buildClaimHistory, claimFamilyId, flipDestinations } from "./claimHistory";

describe("claim history", () => {
  const ledger = buildClaimHistory(scoreboard);

  it("keeps the published family and rerun census", () => {
    expect(ledger.families).toHaveLength(259);
    expect(ledger.runCount).toBe(287);
    expect(ledger.undatedRunCount).toBe(142);
  });

  it("preserves source order for undated reruns", () => {
    const family = ledger.families.find(item => item.hypothesis === "three_in_four_fatigue");
    expect(family?.history.map(run => run.runTs)).toEqual([null, null]);
    expect(family?.history.map(run => run.verdict)).toEqual(["NULL_LOCAL", "CONFIRMED_LOCAL"]);
  });

  it("resolves all five published flip destinations to ledger families", () => {
    const destinations = flipDestinations(ledger);
    expect(destinations).toHaveLength(5);
    expect(destinations.every(family => ledger.families.some(item => claimFamilyId(item) === claimFamilyId(family)))).toBe(true);
  });
});
