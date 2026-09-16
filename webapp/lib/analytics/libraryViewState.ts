import type { Sport } from "./dashboardTypes";
import { readingCollections } from "./readingCollections";

export type LibraryViewState = {
  sport: Sport;
  kind: "all" | "derived" | "source";
  query: string;
  collection: string;
  page: number;
};

const sports = new Set<Sport>(["all", "nba", "mlb", "soccer", "tennis"]);
const kinds = new Set<LibraryViewState["kind"]>(["all", "derived", "source"]);

export function readLibraryViewState(search: string): LibraryViewState {
  const params = new URLSearchParams(search);
  const sport = params.get("sport") as Sport;
  const kind = params.get("kind") as LibraryViewState["kind"];
  const collection = params.get("collection") || "all";
  const page = Number(params.get("page"));
  return {
    sport: sports.has(sport) ? sport : "all",
    kind: kinds.has(kind) ? kind : "all",
    query: params.get("q") || "",
    collection: readingCollections.some((item) => item.id === collection) ? collection : "all",
    page: Number.isInteger(page) && page > 0 ? page : 1,
  };
}

export function libraryViewSearch(search: string, state: LibraryViewState): string {
  const params = new URLSearchParams(search);
  ["sport", "kind", "q", "collection", "page"].forEach((key) => params.delete(key));
  if (state.sport !== "all") params.set("sport", state.sport);
  if (state.kind !== "all") params.set("kind", state.kind);
  if (state.query) params.set("q", state.query);
  if (state.collection !== "all") params.set("collection", state.collection);
  if (state.page > 1) params.set("page", String(state.page));
  return params.toString();
}
