import { describe, expect, it } from "vitest";
import type { Paper } from "./papers";
import { paperViewSearch, readPaperViewState } from "./paperViewState";

const papers = [
  { sport: "nba", keywords: ["rest state", "sample & support"] },
  { sport: "all", keywords: ["Brier score"] },
] as Paper[];

describe("paper view state", () => {
  it("restores a published sport and decoded keyword", () => {
    expect(readPaperViewState("?sport=nba&keyword=rest+state", papers)).toEqual({ sport: "nba", keyword: "rest state" });
  });

  it("keeps cross-sport separate from all papers", () => {
    expect(readPaperViewState("?sport=all", papers).sport).toBe("all");
    expect(readPaperViewState("", papers).sport).toBe("any");
  });

  it("rejects unavailable filter values independently", () => {
    expect(readPaperViewState("?sport=mlb&keyword=rest+state", papers)).toEqual({ sport: "any", keyword: "rest state" });
    expect(readPaperViewState("?sport=nba&keyword=missing", papers)).toEqual({ sport: "nba", keyword: "any" });
    expect(readPaperViewState("?sport=nba&keyword=rest+state", [])).toEqual({ sport: "any", keyword: "any" });
  });

  it("round trips encoded keywords and retains unrelated query values", () => {
    const state = { sport: "nba", keyword: "sample & support" } as const;
    const search = paperViewSearch("?keep=reading&sport=all&keyword=Brier+score&keep=evidence", state);
    expect(readPaperViewState(search, papers)).toEqual(state);
    expect(new URLSearchParams(search).getAll("keep")).toEqual(["reading", "evidence"]);
    expect(new URLSearchParams(search).getAll("sport")).toEqual(["nba"]);
  });

  it("removes only owned filters when reset", () => {
    expect(paperViewSearch("?keep=reading&sport=nba&keyword=rest", { sport: "any", keyword: "any" })).toBe("keep=reading");
  });
});
