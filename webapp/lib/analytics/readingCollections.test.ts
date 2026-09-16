import { describe, expect, it } from "vitest";
import { getLibraryEntries } from "./libraryData";
import { readingCollections, validateReadingCollections } from "./readingCollections";

describe("readingCollections", () => {
  it("keeps every hand-curated route in a published registry", () => {
    expect(validateReadingCollections(getLibraryEntries())).toEqual([]);
  });

  it("keeps collection ids unique and every collection populated", () => {
    expect(new Set(readingCollections.map((collection) => collection.id)).size).toBe(readingCollections.length);
    expect(readingCollections.every((collection) => collection.members.length > 0)).toBe(true);
  });
});
