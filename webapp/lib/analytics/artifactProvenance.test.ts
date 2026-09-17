import { describe, expect, it } from "vitest";
import siteManifest from "@/public/data/showcase/site_manifest.json";
import { artifactDate, artifactUrl, describeDate, provenanceDate } from "./artifactProvenance";

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

  it("distinguishes an as-of date from artifact generation", () => {
    expect(describeDate("2026-07-19T12:00:00Z", "source")).toBe("Source as of 2026-07-19");
    expect(provenanceDate("2026-07-19")).toBe("Source as of 2026-07-19");
    expect(describeDate("2026-02-30", "source")).toBe("Date not published.");
    expect(describeDate({ start: "2024-01-01", end: "2024-12-31" }, "source")).toBe("Date not published.");
  });

  it("formats an explicit published observation window", () => {
    expect(describeDate({ start: "2024-01-01", end: "2024-12-31" }, "window")).toBe(
      "Observation window 2024-01-01 to 2024-12-31"
    );
  });

  it("uses original artifact fields before ambiguous manifest stamps", () => {
    expect(artifactDate({ generated_at: "2026-07-23" }, "2026-07-23")).toEqual({ asOf: "2026-07-23", dateKind: "snapshot" });
    expect(artifactDate({ as_of: "2026-07-19", generated_at: "2026-07-23" }, "2026-07-23")).toEqual({ asOf: "2026-07-19", dateKind: "source" });
    expect(artifactDate({ as_of: "2025-26 regular season" }, "2026-07-23")).toEqual({ asOf: "2025-26 regular season", dateKind: "window" });
    const fallback = artifactDate({}, "2026-07-23");
    expect(describeDate(fallback.asOf, fallback.dateKind)).toBe("Published date 2026-07-23");
  });

  it("never turns a manifest as_of stamp into an observation window", () => {
    const artifact = siteManifest.modules.find(item => item.id === "bookmaker_accuracy");
    expect(describeDate(artifact?.as_of, "window")).toBe("Date not published.");
  });
});

it("keeps a labelled season window and still rejects placeholders", () => {
  expect(describeDate("2025-26 regular season (through 2026-04-12)", "window")).toBe("Observation window 2025-26 regular season (through 2026-04-12)");
  expect(describeDate("Published snapshot", "window")).toBe("Date not published.");
  expect(describeDate("unknown", "window")).toBe("Date not published.");
});
