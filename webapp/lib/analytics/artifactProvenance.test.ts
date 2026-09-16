import { describe, expect, it } from "vitest";
import { artifactUrl, provenanceDate } from "./artifactProvenance";

describe("artifact provenance", () => {
  it("resolves published artifact paths through the configured base path", () => {
    expect(artifactUrl("data/showcase/blowout_dynamics.json", "/court-vision")).toBe(
      "/court-vision/data/showcase/blowout_dynamics.json"
    );
  });

  it("does not create a link for an artifact absent from the export manifest", () => {
    expect(artifactUrl("private_measurement.json", "/court-vision")).toBeNull();
  });

  it("labels missing dates and distinguishes snapshots from observation windows", () => {
    expect(provenanceDate(null)).toBe("date not published");
    expect(provenanceDate("2026-07-25T04:35:33Z")).toBe("snapshot generated: 2026-07-25");
    expect(provenanceDate("2024-25 regular season", "observation_window")).toBe(
      "observation window: 2024-25 regular season"
    );
  });
});
