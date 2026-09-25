import { describe, expect, it } from "vitest";
import { dataIntegrityNotices, integrityRegistrySummary, mlbTickShares, noticesForInspector, noticesForModules, noticesForPaper, status } from "./dataIntegrity";
import { loadIngameIntegrityReceipt, loadIngameRegenerationReceipt, loadIngameTimingRegenerationReceipt } from "@/app/(analytics)/analytics/findings/ingame-join-integrity/ingameJoinIntegrity.server";

describe("dataIntegrity", () => {
  it("resolves each artifact and sport status", () => {
    expect(status("state_conditioned_calibration", "mlb")).toBe("regenerated");
    expect(status("state_conditioned_calibration", "soccer_intl")).toBe("regenerated");
    expect(status("blowout_dynamics", "mlb")).toBe("regenerated");
    expect(status("comeback_atlas", "soccer_intl")).toBe("regenerated");
    expect(status("state_conditioned_calibration", "nba")).toBe("clear");
    expect(status("novel_rest_asymmetry", "nba")).toBe("clear");
    expect(status("ess_ledger", "mlb")).toBe("under-review");
    expect(status("novel_overreaction_harvest_gap", "soccer_intl")).toBe("under-review");
    expect(status("ess_ledger", "nba")).toBe("clear");
  });

  it("keeps the registry artifacts and counts aligned with the incident receipt", () => {
    const receipt = loadIngameIntegrityReceipt();
    expect(receipt.measured_on).toBe(integrityRegistrySummary.measuredOn);
    expect(receipt.exposed_artifacts).toEqual(integrityRegistrySummary.exposedArtifacts);
    expect(receipt.timing_artifacts_under_review).toEqual(integrityRegistrySummary.timingArtifacts);
    expect(receipt.timing_artifacts_under_review).toEqual([]);
    expect(receipt.timing_artifacts_regenerated).toEqual(integrityRegistrySummary.timingRegeneratedArtifacts);
    expect(receipt.per_sport).toEqual(integrityRegistrySummary.perSport);
    expect(receipt.derived_artifacts_under_review).toEqual(integrityRegistrySummary.derivedArtifactsUnderReview);
    expect(receipt.derived_artifacts_under_review.map(entry => entry.artifact))
      .toEqual(["novel_overreaction_harvest_gap", "ess_ledger"]);
    expect(receipt.derived_artifacts_under_review.every(entry => entry.stale_inputs.length > 0)).toBe(true);
  });

  it("states the excluded share and the identified-mismatch share as different numbers", () => {
    const regeneration = loadIngameRegenerationReceipt();
    const receipt = loadIngameIntegrityReceipt();
    const segmentation = regeneration.segmentation.per_sport.mlb;
    expect(mlbTickShares.ticksIn).toBe(segmentation.ticks_in);
    expect(mlbTickShares.excluded).toBe(segmentation.ticks_in - segmentation.ticks_kept);
    expect(mlbTickShares.mismatched).toBe(receipt.per_sport.mlb.mismatched_ticks);
    expect(mlbTickShares.excluded).toBeGreaterThan(mlbTickShares.mismatched);
    expect(mlbTickShares.sentence).toContain("excluded 51,635 of the 78,986 MLB ticks (65.4 percent)");
    expect(mlbTickShares.sentence).toContain("identified label mismatches were a smaller 27,076 (34.3 percent)");
    const reading = regeneration.reading.join(" ");
    expect(reading).not.toMatch(/a third of/i);
    expect(reading).not.toMatch(/widens every/i);
    expect(reading).toContain("27,076 of the 78,986 MLB ticks, 34.3 percent");
    expect(reading).toContain("excluded 51,635, 65.4 percent");
    expect(reading).toContain("excluded 4,738, 52.6 percent");
    expect(loadIngameTimingRegenerationReceipt().reading.join(" ")).not.toMatch(/widens every|a third of/i);
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

  it("distinguishes the timing corpus from each measurement's eligible denominator", () => {
    const timing = loadIngameTimingRegenerationReceipt();
    const notice = noticesForModules(["novel_live_clock_fraction"])[0];
    expect(notice.status).toBe("regenerated");
    expect(notice.summary).toContain(`revision ${timing.revision_published}`);
    expect(notice.summary).toContain(timing.measured_on);
    expect(notice.summary).toContain("stored corpus contains 178 MLB and 27 international soccer games");
    expect(notice.summary).toContain("fewer games after eligibility checks");
    expect(notice.summary).toContain("read their own denominators");
  });

  it("surfaces a regeneration notice for every rebuilt artifact and keeps the review notice unmatched", () => {
    expect(dataIntegrityNotices.map(notice => notice.status)).toEqual(["regenerated", "regenerated", "under-review", "under-review", "under-review"]);
    expect(noticesForModules(["state_conditioned_calibration"])).toMatchObject([{ status: "regenerated" }]);
    expect(noticesForPaper([{ module: "state_conditioned_calibration" }])).toMatchObject([{ status: "regenerated" }]);
    expect(noticesForModules(["blowout_dynamics"])).toMatchObject([{ id: "ingame-timing-regenerated", status: "regenerated" }]);
    expect(noticesForInspector("state-reliability")).toMatchObject([{ status: "regenerated" }]);
    expect(noticesForModules(["ess_ledger"])).toMatchObject([{ id: "derived-review-ess-ledger", status: "under-review" }]);
    expect(noticesForModules(["novel_overreaction_harvest_gap"]))
      .toMatchObject([{ id: "derived-review-novel-overreaction-harvest-gap", status: "under-review" }]);
    expect(noticesForModules(["ess_ledger"])[0].summary).toContain("residual_autocorrelation");
    expect(noticesForModules(["novel_overreaction_harvest_gap"])[0].summary).toContain("market_overreaction");
  });
});
