import { analysisDestinations } from "./analysisDestinations";
import { noticesForModules } from "./dataIntegrity";
import { findingsIndex } from "./findingsIndex";
import { getLibraryEntries } from "./libraryData";
import { loadPapers } from "./papers.server";
import { entityTypeIdentifier, populationIdentifier } from "./readingRelationships";
import { getResearchAnalyses } from "./researchData";
import { relatedReading, type ReadingEntry, type ReadingKind, type RelatedLink } from "./related";

type PaperTarget = { kind: ReadingKind; id: string };
type PaperEntry = ReadingEntry & { targets: PaperTarget[] };

const sportKey = (sport: string) => sport === "soccer_intl" ? "soccer" : sport;
const sameSport = (left: string, right: string) => left === "all" || right === "all" || sportKey(left) === sportKey(right);
const exactSport = (left: string, right: string) => sportKey(left) === sportKey(right);
const sourceIds = (entry: ReadingEntry) => entry.sources || [];

function regeneratedSuffix(moduleIds: readonly string[]): string {
  return noticesForModules(moduleIds).some((notice) => notice.status === "regenerated")
    ? " (sources regenerated)" : "";
}

export function readingEntries(): ReadingEntry[] {
  const library = getLibraryEntries().filter((entry) => entry.kind === "source" || entry.kind === "derived");
  const analyses = new Map(getResearchAnalyses().map((analysis) => [analysis.id, analysis]));
  const papers: PaperEntry[] = loadPapers().map((paper) => ({
    id: paper.slug, title: paper.title, kind: "paper", sport: paper.sport, asOf: paper.date,
    href: `/analytics/papers/${paper.slug}/`, sources: paper.evidence.map((evidence) => evidence.module),
    population: `paper:${sportKey(paper.sport)}`, targets: paper.related as PaperTarget[],
  }));
  return [
    ...library.map((entry) => {
      const analysis = entry.kind === "derived" ? analyses.get(entry.id) : undefined;
      const sources = analysis ? [analysis.source, ...(analysis.sources || []).map((source) => source.id)] : [entry.id];
      const populationInput = { id: entry.id, sport: entry.sport, source: sources[0] };
      return { id: entry.id, title: entry.title, kind: entry.kind === "source" ? "module" as const : "analysis" as const, sport: entry.sport, asOf: entry.asOf, href: entry.href, sources, artifacts: [entry.id, ...sources], population: populationIdentifier(populationInput), entityType: entityTypeIdentifier(populationInput) };
    }),
    ...findingsIndex.map((finding) => {
      const populationInput = { id: finding.slug, sport: finding.sport, source: finding.artifactIds[0] };
      return { id: finding.slug, title: finding.title, kind: "finding" as const, sport: finding.sport, asOf: finding.asOf, href: `/analytics/findings/${finding.slug}/`, sources: finding.artifactIds, artifacts: finding.artifactIds, population: populationIdentifier(populationInput), entityType: entityTypeIdentifier(populationInput) };
    }),
    ...analysisDestinations.map((destination) => ({ id: destination.id, title: destination.title, kind: "inspector" as const, sport: destination.sport, asOf: null, href: destination.route, sources: [...destination.sourceModuleIds], artifacts: [...destination.sourceModuleIds], population: populationIdentifier({ id: destination.id, sport: destination.sport, populationId: destination.populationId }), entityType: entityTypeIdentifier({ id: destination.id, sport: destination.sport, populationId: destination.populationId }), prerequisite: destination.prerequisite })),
    ...papers,
  ];
}

function paperMatches(current: ReadingEntry, paper: PaperEntry): boolean {
  if (!sameSport(current.sport, paper.sport)) return false;
  const direct = paper.targets.some((target) => target.kind === current.kind && target.id === current.id);
  return direct || sourceIds(current).some((source) => paper.sources?.includes(source));
}

/** Returns every sport-compatible paper which explicitly cites this reading or its source module. */
export function paperBacklinks(kind: "module" | "inspector", id: string, entries: ReadingEntry[] = readingEntries()): RelatedLink[] {
  const current = entries.find((entry) => entry.kind === kind && entry.id === id);
  if (!current) return [];
  const suffix = regeneratedSuffix(sourceIds(current));
  return entries.filter((entry): entry is PaperEntry => entry.kind === "paper" && "targets" in entry)
    .filter((paper) => paperMatches(current, paper))
    .map((paper) => ({ id: paper.id, title: `${paper.title}${suffix}`, kind: paper.kind, sport: paper.sport, asOf: paper.asOf, href: paper.href, purpose: "supporting source" as const }))
    .sort((left, right) => left.title.localeCompare(right.title) || left.id.localeCompare(right.id));
}

/** Chooses one explicit inspector return path by source overlap, then sport, then title. */
export function bestPaperForInspector(id: string, entries: ReadingEntry[] = readingEntries()): RelatedLink | null {
  const inspector = entries.find((entry) => entry.kind === "inspector" && entry.id === id);
  if (!inspector) return null;
  const papers = paperBacklinks("inspector", id, entries);
  return papers.sort((left, right) => {
    const leftEntry = entries.find((entry) => entry.kind === "paper" && entry.id === left.id)!;
    const rightEntry = entries.find((entry) => entry.kind === "paper" && entry.id === right.id)!;
    const sourceOverlap = (entry: ReadingEntry) => sourceIds(inspector).filter((source) => sourceIds(entry).includes(source)).length;
    return sourceOverlap(rightEntry) - sourceOverlap(leftEntry) || Number(exactSport(inspector.sport, right.sport)) - Number(exactSport(inspector.sport, left.sport)) || left.title.localeCompare(right.title);
  })[0] || null;
}

export function relatedReadingFor(kind: ReadingKind, id: string, entries: ReadingEntry[] = readingEntries()): RelatedLink[] {
  return relatedReading(kind, id, entries);
}
