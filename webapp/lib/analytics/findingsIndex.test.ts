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
});
