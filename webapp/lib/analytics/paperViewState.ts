import { paperKeywords, paperSports, type Paper, type PaperSport } from "./papers";

export type PaperViewState = { sport: PaperSport | "any"; keyword: string };

export function readPaperViewState(search: string, papers: Paper[]): PaperViewState {
  const params = new URLSearchParams(search);
  const sport = params.get("sport") as PaperSport;
  const keyword = params.get("keyword") || "any";
  return {
    sport: paperSports(papers).includes(sport) ? sport : "any",
    keyword: paperKeywords(papers).includes(keyword) ? keyword : "any",
  };
}

export function paperViewSearch(search: string, state: PaperViewState): string {
  const params = new URLSearchParams(search);
  params.delete("sport");
  params.delete("keyword");
  if (state.sport !== "any") params.set("sport", state.sport);
  if (state.keyword !== "any") params.set("keyword", state.keyword);
  return params.toString();
}
