import type { Sport } from "./dashboardTypes";
import type { LibrarySourceSummary } from "./librarySourceSummaries";
export type LibraryAvailability = "published" | "partial" | "unavailable";
export type LibraryEntryKind = "derived" | "source" | "finding" | "inspector" | "explainer" | "paper";
export type LibraryEntry = {
  id: string; title: string; description: string; category: string; sport: Sport;
  kind: LibraryEntryKind; kindLabel: string; status: string; href: string; asOf: string | null;
  keywords: string; rows: number | null; fields: number | null;
  preview: number[]; previewLabel: string;
  sourceSummary?: LibrarySourceSummary;
  integrityNotice?: string;
};
export function filterLibrary(entries: LibraryEntry[], sport: Sport, kind: string, query: string, collectionIds: string[] = []) {
  const terms = query.toLowerCase().trim().split(/\s+/).filter(Boolean);
  return entries.filter(e => (sport === "all" || e.sport === sport || e.sport === "all") &&
    (kind === "all" || e.kind === kind) && (!collectionIds.length || collectionIds.includes(e.id)) &&
    terms.every(t => `${e.title} ${e.description} ${e.category} ${e.keywords}`.toLowerCase().includes(t)));
}
