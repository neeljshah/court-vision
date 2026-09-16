import type { Sport } from "./dashboardTypes";
import type { LibrarySourceSummary } from "./librarySourceSummaries";
export type LibraryAvailability = "published" | "partial" | "unavailable";
export type LibraryEntry = {
  id: string; title: string; description: string; category: string; sport: Sport;
  kind: "derived" | "source"; status: string; href: string; asOf: string | null;
  keywords: string; rows: number | null; fields: number | null;
  preview: number[]; previewLabel: string;
  sourceSummary?: LibrarySourceSummary;
};
export function filterLibrary(entries: LibraryEntry[], sport: Sport, kind: string, query: string) {
  const terms = query.toLowerCase().trim().split(/\s+/).filter(Boolean);
  return entries.filter(e => (sport === "all" || e.sport === sport || e.sport === "all") &&
    (kind === "all" || e.kind === kind) && terms.every(t => `${e.title} ${e.description} ${e.category} ${e.keywords}`.toLowerCase().includes(t)));
}
