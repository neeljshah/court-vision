import { describe, expect, it } from "vitest";
import { findingsIndex } from "./findingsIndex";
import { getLibraryEntries } from "./libraryData";
import { readingCollections, validateReadingCollections } from "./readingCollections";
import { analysisDestinations } from "./analysisDestinations";

describe("readingCollections", () => {
  it("keeps every hand-curated route in a published registry", () => {
    expect(validateReadingCollections(getLibraryEntries(), findingsIndex.map((finding) => finding.slug))).toEqual([]);
  });

  it("keeps collection ids unique and every collection populated", () => {
    expect(new Set(readingCollections.map((collection) => collection.id)).size).toBe(readingCollections.length);
    expect(readingCollections.every((collection) => collection.members.length > 0)).toBe(true);
  });

  it("places every inspector in an authored collection", () => {
    const memberIds = new Set(readingCollections.flatMap((collection) => collection.members.map((member) => member.id)));
    expect(analysisDestinations.every((destination) => memberIds.has(destination.id))).toBe(true);
    expect(memberIds.size).toBeGreaterThan(analysisDestinations.length);
  });
});
