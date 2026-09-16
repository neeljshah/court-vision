import { describe, expect, it } from "vitest";
import { dataIntegrityNotices, noticesForInspector, noticesForModules, noticesForPaper } from "./dataIntegrity";

describe("dataIntegrity", () => {
  it("publishes the measured MLB in-game join notice", () => {
    const notice = dataIntegrityNotices[0];
    expect(dataIntegrityNotices).toHaveLength(1);
    expect(notice).toMatchObject({ id: "mlb-ingame-join-integrity", measuredOn: "2026-09-16", exposure: "label-contamination", status: "pending-regeneration" });
    expect(notice.summary).toContain("126 of 227");
    expect(notice.summary).toContain("27,076 of 78,986");
  });

  it("resolves affected artifacts but leaves unaffected ones clear", () => {
    expect(noticesForModules(["state_conditioned_calibration"])).toHaveLength(1);
    expect(noticesForPaper([{ module: "state_conditioned_calibration" }])).toHaveLength(1);
    expect(noticesForModules(["blowout_dynamics"])).toHaveLength(0);
    expect(noticesForInspector("state-reliability")).toHaveLength(1);
  });
});
