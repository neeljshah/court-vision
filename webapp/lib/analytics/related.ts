import { analysisDestinations } from "./analysisDestinations";
import { findingsIndex } from "./findingsIndex";
import { collectionMemberIds, readingCollections } from "./readingCollections";
import { isAuthoredPrerequisite } from "./readingRelationships";
import { getResearchAnalyses } from "./researchData";
import type { ResearchAnalysis } from "./researchTypes";

export type ReadingKind = "module" | "analysis" | "finding" | "inspector" | "explainer" | "paper";
export type RelatedPurpose = "prerequisite" | "same population" | "same entity type" | "same sport" | "same source file" | "supporting source" | "next question";
export type RelatedLink = {
  id: string; title: string; kind: ReadingKind; sport: string; asOf: string | null; href: string; purpose: RelatedPurpose; prerequisite?: string;
};
export type ReadingEntry = Omit<RelatedLink, "purpose"> & {
  sources?: string[]; artifacts?: string[]; population: string; entityType?: string;
};
export type JoinedFindingTarget = Pick<RelatedLink, "id" | "title" | "href" | "kind">;

const words = (title: string) => new Set(title.toLowerCase().match(/[a-z0-9]{4,}/g) || []);
const overlap = (left: string, right: string) => [...words(left)].filter((word) => words(right).has(word)).length;
const collectionIds = (id: string) => new Set(readingCollections.filter((collection) => collectionMemberIds(collection.id).includes(id)).map((collection) => collection.id));
const sharedCollection = (left: string, right: string) => [...collectionIds(left)].some((id) => collectionIds(right).has(id));
const sourceIds = (entry: ReadingEntry) => entry.sources || [];

function relation(current: ReadingEntry, entry: ReadingEntry): { score: number; purpose: RelatedPurpose } | null {
  const currentSources = sourceIds(current), entrySources = sourceIds(entry);
  const directSource = currentSources.includes(entry.id) || entrySources.includes(current.id);
  const sharedSource = currentSources.some((source) => entrySources.includes(source));
  const sharedArtifact = !!current.artifacts?.some((artifact) => entry.artifacts?.includes(artifact));
  const sameSport = current.sport !== "all" && entry.sport === current.sport;
  const samePopulation = current.population === entry.population;
  const sameEntityType = sameSport && !!current.entityType && current.entityType === entry.entityType;
  if (directSource) return { score: 400, purpose: "supporting source" };
  if (sharedSource) return { score: 350, purpose: "same source file" };
  if (sharedArtifact) return { score: 340, purpose: "supporting source" };
  if (samePopulation) return { score: 325, purpose: "same population" };
  if (sameEntityType) return { score: 300, purpose: "same entity type" };
  if (isAuthoredPrerequisite(current.id, entry.id)) return { score: 275, purpose: "prerequisite" };
  if (sharedCollection(current.id, entry.id)) return { score: 250, purpose: "next question" };
  if (sameSport) return { score: 150, purpose: "same sport" };
  return null;
}

/** Scores already-published reading entries. Filesystem-backed entry loading lives in related.server.ts. */
export function relatedReading(kind: ReadingKind, id: string, entries: readonly ReadingEntry[]): RelatedLink[] {
  const current = entries.find((entry) => entry.kind === kind && entry.id === id);
  if (!current) return [];
  return entries.filter((entry) => entry !== current).map((entry) => {
    const related = relation(current, entry);
    return related && { entry, ...related, shared: overlap(current.title, entry.title) };
  }).filter((item): item is { entry: ReadingEntry; score: number; purpose: RelatedPurpose; shared: number } => !!item)
    .sort((left, right) => right.score - left.score || right.shared - left.shared || left.entry.title.localeCompare(right.entry.title) || left.entry.id.localeCompare(right.entry.id))
    .slice(0, 6).map(({ entry, purpose }) => ({ id: entry.id, title: entry.title, kind: entry.kind, sport: entry.sport, asOf: entry.asOf, href: entry.href, purpose, prerequisite: entry.prerequisite }));
}

function artifactModuleId(sourceArtifact: string): string {
  const filename = sourceArtifact.split(/[\\/]/).pop() || sourceArtifact;
  return filename.replace(/\.json$/i, "");
}

/** Resolves entity-card artifacts through the pure research registry. */
export function joinedFindingTarget(sourceArtifact: string, analyses: ResearchAnalysis[] = getResearchAnalyses()): JoinedFindingTarget | null {
  const sourceId = artifactModuleId(sourceArtifact);
  const matches = analyses.filter((analysis) => analysis.source === sourceId || analysis.sources?.some((source) => source.id === sourceId))
    .sort((left, right) => left.title.localeCompare(right.title) || left.id.localeCompare(right.id));
  if (matches[0]) return { id: matches[0].id, title: matches[0].title, href: `/analytics/research/${matches[0].id}/`, kind: "analysis" };
  return null;
}

/** @deprecated Server components should load the complete graph from related.server.ts. */
export function readingEntries(): ReadingEntry[] {
  return [
    ...getResearchAnalyses().map((analysis) => ({ id: analysis.id, title: analysis.title, kind: "analysis" as const, sport: analysis.sport, asOf: analysis.asOf || null, href: `/analytics/research/${analysis.id}/`, population: `analysis:${analysis.id}` })),
    ...findingsIndex.map((finding) => ({ id: finding.slug, title: finding.title, kind: "finding" as const, sport: finding.sport, asOf: finding.asOf, href: `/analytics/findings/${finding.slug}/`, population: `finding:${finding.slug}` })),
    ...analysisDestinations.map((destination) => ({ id: destination.id, title: destination.title, kind: "inspector" as const, sport: destination.sport, asOf: null, href: destination.route, population: destination.populationId, prerequisite: destination.prerequisite })),
  ];
}
