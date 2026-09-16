import { describe, expect, it } from "vitest";
import { findingsIndex } from "./findingsIndex";
import { snapshot } from "./labHelpers";
import { getResearchAnalyses } from "./researchData";
import { readingCollections, validateReadingCollections } from "./readingCollections";

describe("readingCollections", () => {
  it("keeps every hand-curated route in a published registry", () => {
    const manifest = snapshot<{ modules: { id: string }[] }>("site_manifest");
    expect(validateReadingCollections(getResearchAnalyses(), findingsIndex, manifest.modules.map((item) => item.id))).toEqual([]);
  });

  it("keeps collection ids unique and every collection populated", () => {
    expect(new Set(readingCollections.map((collection) => collection.id)).size).toBe(readingCollections.length);
    expect(readingCollections.every((collection) => collection.members.length > 0)).toBe(true);
  });
});
