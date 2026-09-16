import { findingsIndex } from "./findingsIndex";
import { getLibraryEntries } from "./libraryData";
import { getResearchAnalyses } from "./researchData";

export type ReadingKind = "module" | "analysis" | "finding";
export type RelatedLink = { id: string; title: string; kind: ReadingKind; sport: string; asOf: string | null; href: string };
type Candidate = RelatedLink & { source?: string; artifacts?: string[] };

const words = (title: string) => new Set(title.toLowerCase().match(/[a-z0-9]{4,}/g) || []);
const overlap = (left: string, right: string) => [...words(left)].filter(word => words(right).has(word)).length;

export function relatedReading(kind: ReadingKind, id: string, entries: Candidate[] = readingEntries()): RelatedLink[] {
  const current = entries.find(entry => entry.kind === kind && entry.id === id);
  if (!current) return [];
  return entries.filter(entry => entry !== current).map(entry => {
    const sameSource = current.source && entry.source && current.source === entry.source;
    const sameArtifact = !!current.artifacts?.some(artifact => entry.artifacts?.includes(artifact));
    const sameSport = current.sport !== "all" && entry.sport === current.sport;
    return { entry, score: sameSource ? 400 : sameArtifact ? 300 : sameSport ? 200 : overlap(current.title, entry.title) ? 100 : 0, shared: overlap(current.title, entry.title) };
  }).filter(item => item.score > 0).sort((left, right) =>
    right.score - left.score || right.shared - left.shared || left.entry.title.localeCompare(right.entry.title) || left.entry.id.localeCompare(right.entry.id)
  ).slice(0, 6).map(({ entry }) => ({ id: entry.id, title: entry.title, kind: entry.kind, sport: entry.sport, asOf: entry.asOf, href: entry.href }));
}

export function readingEntries(): Candidate[] {
  const library = getLibraryEntries();
  const sources = new Map(getResearchAnalyses().map(analysis => [analysis.id, analysis.source]));
  return [
    ...library.map(entry => ({ id: entry.id, title: entry.title, kind: entry.kind === "source" ? "module" as const : "analysis" as const, sport: entry.sport, asOf: entry.asOf, href: entry.href, source: entry.kind === "derived" ? sources.get(entry.id) : entry.id, artifacts: [entry.id] })),
    ...findingsIndex.map(finding => ({ id: finding.slug, title: finding.title, kind: "finding" as const, sport: finding.sport, asOf: finding.asOf, href: `/analytics/findings/${finding.slug}/`, artifacts: finding.artifactIds })),
  ];
}
