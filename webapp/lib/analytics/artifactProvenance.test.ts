import { describe, expect, it } from "vitest";
import siteManifest from "@/public/data/showcase/site_manifest.json";
import { artifactUrl, describeDate } from "./artifactProvenance";

describe("artifact provenance", () => {
  it("resolves published artifact paths through the configured base path", () => {
    expect(artifactUrl("data/showcase/blowout_dynamics.json", "/court-vision")).toBe(
      "/court-vision/data/showcase/blowout_dynamics.json"
    );
  });

  it("does not create a link for an artifact absent from the export manifest", () => {
    expect(artifactUrl("private_measurement.json", "/court-vision")).toBeNull();
  });

  it("formats only a valid ISO snapshot date", () => {
    expect(describeDate("Published snapshot", "snapshot")).toBe("Date not published.");
    expect(describeDate("2026-07-25T04:35:33Z", "snapshot")).toBe("Snapshot generated 2026-07-25");
  });

  it("formats an explicit published observation window", () => {
    expect(describeDate({ start: "2024-01-01", end: "2024-12-31" }, "window")).toBe(
      "Observation window 2024-01-01 to 2024-12-31"
    );
  });

  it("never turns a manifest as_of stamp into an observation window", () => {
    const artifact = siteManifest.modules.find(item => item.id === "bookmaker_accuracy");
    expect(describeDate(artifact?.as_of, "window")).toBe("Date not published.");
  });
});
