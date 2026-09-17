import { describe, expect, it } from "vitest";
import { dataIntegrityNotices, integrityRegistrySummary, noticesForInspector, noticesForModules, noticesForPaper, status } from "./dataIntegrity";
import { loadIngameIntegrityReceipt, loadIngameRegenerationReceipt, loadIngameTimingRegenerationReceipt } from "@/app/(analytics)/analytics/findings/ingame-join-integrity/ingameJoinIntegrity.server";

describe("dataIntegrity", () => {
  it("resolves each artifact and sport status", () => {
    expect(status("state_conditioned_calibration", "mlb")).toBe("regenerated");
    expect(status("state_conditioned_calibration", "soccer_intl")).toBe("regenerated");
    expect(status("blowout_dynamics", "mlb")).toBe("regenerated");
    expect(status("comeback_atlas", "soccer_intl")).toBe("regenerated");
    expect(status("state_conditioned_calibration", "nba")).toBe("clear");
    expect(status("novel_rest_asymmetry", "nba")).toBe("clear");
  });

  it("keeps the registry artifacts and counts aligned with the incident receipt", () => {
    const receipt = loadIngameIntegrityReceipt();
    expect(receipt.measured_on).toBe(integrityRegistrySummary.measuredOn);
    expect(receipt.exposed_artifacts).toEqual(integrityRegistrySummary.exposedArtifacts);
    expect(receipt.timing_artifacts_under_review).toEqual(integrityRegistrySummary.timingArtifacts);
    expect(receipt.timing_artifacts_under_review).toEqual([]);
    expect(receipt.timing_artifacts_regenerated).toEqual(integrityRegistrySummary.timingRegeneratedArtifacts);
    expect(receipt.per_sport).toEqual(integrityRegistrySummary.perSport);
  });

  it("publishes every exposed artifact at the regeneration receipt's revision", () => {
    const regeneration = loadIngameRegenerationReceipt();
    expect(regeneration.revision_published).toBe(integrityRegistrySummary.revisionPublished);
    expect(regeneration.artifacts.map(row => row.artifact).sort())
      .toEqual([...integrityRegistrySummary.exposedArtifacts].sort());
    expect(regeneration.artifacts.every(row => row.n_after <= row.n_before)).toBe(true);
  });

  it("publishes every timing artifact at the timing receipt's revision", () => {
    const timing = loadIngameTimingRegenerationReceipt();
    expect(timing.revision_published).toBe(integrityRegistrySummary.revisionPublished);
    expect(timing.measured_on).toBe(integrityRegistrySummary.timingMeasuredOn);
    expect(timing.artifacts.map(row => row.artifact).sort())
      .toEqual([...integrityRegistrySummary.timingRegeneratedArtifacts].sort());
    expect(timing.artifacts.every(row => row.n_after <= row.n_before)).toBe(true);
  });

  it("surfaces a regeneration notice for every rebuilt artifact and keeps the review notice unmatched", () => {
    expect(dataIntegrityNotices.map(notice => notice.status)).toEqual(["regenerated", "regenerated", "under-review"]);
    expect(noticesForModules(["state_conditioned_calibration"])).toMatchObject([{ status: "regenerated" }]);
    expect(noticesForPaper([{ module: "state_conditioned_calibration" }])).toMatchObject([{ status: "regenerated" }]);
    expect(noticesForModules(["blowout_dynamics"])).toMatchObject([{ id: "ingame-timing-regenerated", status: "regenerated" }]);
    expect(noticesForInspector("state-reliability")).toMatchObject([{ status: "regenerated" }]);
  });
});
