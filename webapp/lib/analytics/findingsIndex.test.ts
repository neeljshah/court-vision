import { readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { findingsIndex } from "./findingsIndex";

describe("findingsIndex", () => {
  it("maps every findings route exactly once", () => {
    const routes = readdirSync(join(process.cwd(), "app", "(analytics)", "analytics", "findings"), { withFileTypes: true })
      .filter(entry => entry.isDirectory()).map(entry => entry.name).sort();
    const registered = findingsIndex.map(finding => finding.slug).sort();
    expect(new Set(registered).size).toBe(registered.length);
    expect(registered).toEqual(routes);
  });

  it("registers the MLB in-game integrity exhibit with exposed artifacts", () => {
    const finding = findingsIndex.find(entry => entry.slug === "ingame-join-integrity");
    expect(finding).toMatchObject({ sport: "mlb", asOf: "2026-09-16" });
    expect(finding?.artifactIds).toContain("state_conditioned_calibration");
    expect(finding?.artifactIds).not.toContain("blowout_dynamics");
  });
});
