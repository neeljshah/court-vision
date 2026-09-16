import { describe, expect, it } from "vitest";
import { AUTHORED_PREREQUISITES, isAuthoredPrerequisite, populationIdentifier } from "./readingRelationships";

describe("reading relationships", () => {
  it("derives distinct MLB pitch-type and batter population identifiers", () => {
    expect(populationIdentifier({ id: "mlb-velocity-shape", source: "statcast_showcase", sport: "mlb" })).toBe("mlb pitch types");
    expect(populationIdentifier({ id: "mlb-batter-p90-minus-mean-exit-velocity", source: "atlas_mlb_batters_manifest", sport: "mlb" })).toBe("mlb batters");
  });

  it("uses the same identifier for a source module and analysis of its calibration bins", () => {
    expect(populationIdentifier({ id: "calibration_stability", sport: "all" })).toBe("all calibration bins");
    expect(populationIdentifier({ id: "signed-calibration-direction", source: "calibration_stability", sport: "all" })).toBe("all calibration bins");
  });

  it("only exposes authored prerequisite pairs", () => {
    expect(isAuthoredPrerequisite("calibration", "reliability")).toBe(true);
    expect(isAuthoredPrerequisite("observation-dependence", "effective-sample-size")).toBe(true);
    expect(isAuthoredPrerequisite("mlb-velocity-shape", "mlb-batter-p90-minus-mean-exit-velocity")).toBe(false);
    expect(AUTHORED_PREREQUISITES["pitch_sequencing"]).toContain("mlb-pitch-mix-concentration");
  });
});
