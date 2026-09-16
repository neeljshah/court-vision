import { describe, expect, it } from "vitest";
import { dataIntegrityNotices, integrityRegistrySummary, noticesForInspector, noticesForModules, noticesForPaper, status } from "./dataIntegrity";
import { loadIngameIntegrityReceipt } from "@/app/(analytics)/analytics/findings/ingame-join-integrity/ingameJoinIntegrity.server";

describe("dataIntegrity", () => {
  it("resolves each artifact and sport status", () => {
    expect(status("state_conditioned_calibration", "mlb")).toBe("withdrawn-pending-regeneration");
    expect(status("state_conditioned_calibration", "soccer_intl")).toBe("under-review");
    expect(status("blowout_dynamics", "mlb")).toBe("under-review");
    expect(status("novel_rest_asymmetry", "nba")).toBe("clear");
  });

  it("keeps the registry artifacts and counts aligned with the incident receipt", () => {
    const receipt = loadIngameIntegrityReceipt();
    expect(receipt.measured_on).toBe(integrityRegistrySummary.measuredOn);
    expect(receipt.exposed_artifacts).toEqual(integrityRegistrySummary.exposedArtifacts);
    expect(receipt.timing_artifacts_under_review).toEqual(integrityRegistrySummary.timingArtifacts);
    expect(receipt.per_sport).toEqual(integrityRegistrySummary.perSport);
  });

  it("surfaces withdrawal and review notices for affected artifacts", () => {
    expect(dataIntegrityNotices.map(notice => notice.status)).toEqual(["withdrawn-pending-regeneration", "under-review"]);
    expect(noticesForModules(["state_conditioned_calibration"])).toHaveLength(2);
    expect(noticesForPaper([{ module: "state_conditioned_calibration" }])).toHaveLength(2);
    expect(noticesForModules(["blowout_dynamics"])).toMatchObject([{ status: "under-review" }]);
    expect(noticesForInspector("state-reliability")).toHaveLength(2);
  });
});
