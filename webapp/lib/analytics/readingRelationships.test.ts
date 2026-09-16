import { describe, expect, it } from "vitest";
import { AUTHORED_PREREQUISITES, entityTypeIdentifier, isAuthoredPrerequisite, populationIdentifier } from "./readingRelationships";

describe("reading relationships", () => {
  it("gives pitch readings one population and keeps team and count readings separate", () => {
    const pitch = populationIdentifier({ id: "mlb-velocity-shape", source: "statcast_showcase", sport: "mlb" });
    expect(pitch).toBe("mlb_pitch_types");
    expect(populationIdentifier({ id: "mlb-pitch-mix-concentration", source: "statcast_showcase", sport: "mlb" })).toBe(pitch);
    expect(populationIdentifier({ id: "mlb-team-measurements", sport: "mlb", populationId: "mlb_teams" })).not.toBe(pitch);
    expect(populationIdentifier({ id: "mlb-count-contrast", source: "mlb_count_leverage", sport: "mlb" })).not.toBe(pitch);
  });

  it("uses an analysis-specific fallback instead of treating a shared source as a population", () => {
    expect(populationIdentifier({ id: "unclassified-analysis", source: "shared_source", sport: "all" })).toBe("analysis:unclassified-analysis");
    expect(populationIdentifier({ id: "calibration_stability", sport: "all" })).toBe("cross_sport_calibration_bins");
  });

  it("keeps entity type broader than an exact population identifier", () => {
    expect(entityTypeIdentifier({ id: "sequence", sport: "mlb", populationId: "mlb_pitch_sequences" })).toBe("pitch type");
    expect(entityTypeIdentifier({ id: "type", sport: "mlb", populationId: "mlb_pitch_types" })).toBe("pitch type");
  });

  it("only exposes authored prerequisite pairs", () => {
    expect(isAuthoredPrerequisite("calibration", "reliability")).toBe(true);
    expect(isAuthoredPrerequisite("observation-dependence", "effective-sample-size")).toBe(true);
    expect(isAuthoredPrerequisite("mlb-velocity-shape", "mlb-batter-p90-minus-mean-exit-velocity")).toBe(false);
    expect(AUTHORED_PREREQUISITES["pitch-sequencing"]).toContain("mlb-pitch-mix-concentration");
  });
});
