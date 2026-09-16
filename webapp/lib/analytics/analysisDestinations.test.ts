import { existsSync } from "node:fs";
import { join } from "node:path";
import { snapshot } from "./labHelpers";
import { describe, expect, it } from "vitest";
import { analysisDestinations, inspectorSearchRecords } from "./analysisDestinations";

describe("analysis destinations", () => {
  it("points only to fixed inspector routes and published source modules", () => {
    const manifest = snapshot<{ modules: Array<{ id: string }> }>("site_manifest");
    const moduleIds = new Set(manifest.modules.map(entry => entry.id));
    const routes = new Set(["/analytics/calibration", "/analytics/state-reliability", "/analytics/pitch-sequencing", "/analytics/score-decomposition", "/analytics/observation-dependence", "/analytics/residual-anatomy", "/analytics/blowout-timing", "/analytics/state-contrasts"]);
    expect(new Set(analysisDestinations.map(destination => destination.route))).toEqual(routes);
    analysisDestinations.forEach(destination => {
      expect(routes.has(destination.route)).toBe(true);
      expect(existsSync(join(process.cwd(), "app/(analytics)", `${destination.route.replace("/analytics/", "analytics/")}/page.tsx`))).toBe(true);
      destination.sourceModuleIds.forEach(id => expect(moduleIds.has(id)).toBe(true));
    });
  });

  it("builds a page search record for every inspector", () => {
    const records = inspectorSearchRecords();
    expect(records).toHaveLength(analysisDestinations.length);
    expect(records.every(record => record.type === "page")).toBe(true);
    expect(records.map(record => record.href)).toEqual(analysisDestinations.map(destination => destination.route));
  });
});
