import { findingsIndex } from "./findingsIndex";
import { getLibraryEntries } from "./libraryData";
import { collectionMemberIds, readingCollections } from "./readingCollections";
import { getResearchAnalyses } from "./researchData";
import type { ResearchAnalysis } from "./researchTypes";
import { isAuthoredPrerequisite, populationIdentifier } from "./readingRelationships";
import { analysisDestinations } from "./analysisDestinations";

export type ReadingKind = "module" | "analysis" | "finding" | "inspector";
export type RelatedPurpose = "prerequisite" | "same population" | "same sport" | "same source file" | "supporting source" | "next question";
export type RelatedLink = {
  id: string; title: string; kind: ReadingKind; sport: string; asOf: string | null; href: string; purpose: RelatedPurpose; prerequisite?: string;
};
type Candidate = Omit<RelatedLink, "purpose"> & { sources?: string[]; artifacts?: string[]; population: string };
export type JoinedFindingTarget = Pick<RelatedLink, "id" | "title" | "href" | "kind">;

const words = (title: string) => new Set(title.toLowerCase().match(/[a-z0-9]{4,}/g) || []);
const overlap = (left: string, right: string) => [...words(left)].filter((word) => words(right).has(word)).length;
const collectionIds = (id: string) => new Set(readingCollections.filter((collection) => collectionMemberIds(collection.id).includes(id)).map((collection) => collection.id));
const sharedCollection = (left: string, right: string) => [...collectionIds(left)].some((id) => collectionIds(right).has(id));
const sourceIds = (entry: Candidate) => entry.sources || [];

function relation(current: Candidate, entry: Candidate): { score: number; purpose: RelatedPurpose } | null {
  const currentSources = sourceIds(current), entrySources = sourceIds(entry);
  const directSource = currentSources.includes(entry.id) || entrySources.includes(current.id);
  const sharedSource = currentSources.some((source) => entrySources.includes(source));
  const sharedArtifact = !!current.artifacts?.some((artifact) => entry.artifacts?.includes(artifact));
  const sameSport = current.sport !== "all" && entry.sport === current.sport;
  const samePopulation = current.population === entry.population;
  const titleOverlap = overlap(current.title, entry.title);
  if (directSource) return { score: 400, purpose: "supporting source" };
  if (sharedSource) return { score: 350, purpose: "same source file" };
  if (sharedArtifact) return { score: 340, purpose: "supporting source" };
  if (samePopulation) return { score: 325, purpose: "same population" };
  if (isAuthoredPrerequisite(current.id, entry.id)) return { score: 275, purpose: "prerequisite" };
  if (sharedCollection(current.id, entry.id)) return { score: 250, purpose: "next question" };
  if (sameSport) return { score: 150, purpose: "same sport" };
  return null;
}

export function relatedReading(kind: ReadingKind, id: string, entries: Candidate[] = readingEntries()): RelatedLink[] {
  const current = entries.find((entry) => entry.kind === kind && entry.id === id);
  if (!current) return [];
  return entries.filter((entry) => entry !== current).map((entry) => {
    const related = relation(current, entry);
    return related && { entry, ...related, shared: overlap(current.title, entry.title) };
  }).filter((item): item is { entry: Candidate; score: number; purpose: RelatedPurpose; shared: number } => !!item)
    .sort((left, right) => right.score - left.score || right.shared - left.shared || left.entry.title.localeCompare(right.entry.title) || left.entry.id.localeCompare(right.entry.id))
    .slice(0, 6).map(({ entry, purpose }) => ({ id: entry.id, title: entry.title, kind: entry.kind, sport: entry.sport, asOf: entry.asOf, href: entry.href, purpose, prerequisite: entry.prerequisite }));
}

export function readingEntries(): Candidate[] {
  const library = getLibraryEntries();
  const analyses = new Map(getResearchAnalyses().map((analysis) => [analysis.id, analysis]));
  return [
    ...library.map((entry) => {
      const analysis = entry.kind === "derived" ? analyses.get(entry.id) : undefined;
      const sources = analysis ? [analysis.source, ...(analysis.sources || []).map((source) => source.id)] : [entry.id];
      return { id: entry.id, title: entry.title, kind: entry.kind === "source" ? "module" as const : "analysis" as const, sport: entry.sport, asOf: entry.asOf, href: entry.href, sources, artifacts: [entry.id, ...sources], population: populationIdentifier({ id: entry.id, sport: entry.sport, source: analysis?.source }) };
    }),
    ...findingsIndex.map((finding) => ({ id: finding.slug, title: finding.title, kind: "finding" as const, sport: finding.sport, asOf: finding.asOf, href: `/analytics/findings/${finding.slug}/`, sources: finding.artifactIds, artifacts: finding.artifactIds, population: populationIdentifier({ id: finding.slug, sport: finding.sport, source: finding.artifactIds[0] }) })),
    ...analysisDestinations.map((destination) => ({
      id: destination.id, title: destination.title, kind: "inspector" as const,
      sport: destination.sport, asOf: null, href: destination.route,
      sources: [...destination.sourceModuleIds], artifacts: [...destination.sourceModuleIds],
      population: populationIdentifier({ id: destination.id, sport: destination.sport, populationId: destination.populationId }),
      prerequisite: destination.prerequisite,
    })),
  ];
}

function artifactModuleId(sourceArtifact: string): string {
  const filename = sourceArtifact.split(/[\\/]/).pop() || sourceArtifact;
  return filename.replace(/\.json$/i, "");
}

export function joinedFindingTarget(
  sourceArtifact: string,
  analyses: ResearchAnalysis[] = getResearchAnalyses(),
  entries?: ReturnType<typeof getLibraryEntries>,
): JoinedFindingTarget | null {
  const sourceId = artifactModuleId(sourceArtifact);
  const matches = analyses.filter((analysis) => analysis.source === sourceId || analysis.sources?.some((source) => source.id === sourceId))
    .sort((left, right) => left.title.localeCompare(right.title) || left.id.localeCompare(right.id));
  if (matches[0]) return { id: matches[0].id, title: matches[0].title, href: `/analytics/research/${matches[0].id}/`, kind: "analysis" };
  const sourceEntry = (entries || getLibraryEntries()).find((entry) => entry.kind === "source" && entry.id === sourceId);
  return sourceEntry ? { id: sourceEntry.id, title: sourceEntry.title, href: sourceEntry.href, kind: "module" } : null;
}
