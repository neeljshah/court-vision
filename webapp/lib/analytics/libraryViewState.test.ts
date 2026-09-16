import { describe, expect, it } from "vitest";
import { libraryViewSearch, readLibraryViewState } from "./libraryViewState";

describe("libraryViewState", () => {
  it("reads filters and a positive one-based page", () => {
    expect(readLibraryViewState("?sport=nba&kind=derived&q=pace&collection=forecast-calibration&page=2")).toMatchObject({
      sport: "nba", kind: "derived", query: "pace", collection: "forecast-calibration", page: 2,
    });
  });

  it("falls back to page one without rewriting an invalid URL value", () => {
    expect(readLibraryViewState("?page=none").page).toBe(1);
    expect(libraryViewSearch("?keep=reading", { sport: "all", kind: "all", query: "", collection: "all", page: 1 })).toBe("keep=reading");
  });
});
