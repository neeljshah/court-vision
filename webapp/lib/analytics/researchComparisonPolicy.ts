import { researchPopulationIds, UNKNOWN_POPULATION_KEY, UNKNOWN_POPULATION_LABEL, type ResearchPopulationContext } from "./researchPopulations";
import type { ResearchRow } from "./researchTypes";

export type ResearchCompatibility = "compatible" | "incompatible" | "unknown";
export type ResearchPopulation = {
  key: string;
  label: string;
  sport?: string;
  rowCount: number;
  rowIds: string[];
  compatibility: ResearchCompatibility;
};
export type ResearchComparisonPolicy = {
  compatibility: ResearchCompatibility;
  compatible: boolean;
  populations: ResearchPopulation[];
  aggregateRows: ResearchRow[];
  reason: string;
};

export function matchesResearchPopulation(row: ResearchRow, population: ResearchPopulation) {
  return population.rowIds.includes(row.id);
}

export function researchComparisonPolicy(rows: ResearchRow[], analysis?: ResearchPopulationContext): ResearchComparisonPolicy {
  const ids = researchPopulationIds(rows, analysis);
  const aggregateRows = rows.filter((_, index) => ids[index].aggregate);
  const incomplete = ids.some(identity => !identity.known);
  const components = ids.filter(identity => identity.known && !identity.aggregate);
  const componentKeys = [...new Set(components.map(identity => identity.key))];
  const mixedAggregate = aggregateRows.length > 0 && components.length > 0;
  const compatibility: ResearchCompatibility = !rows.length ? "compatible"
    : incomplete ? "unknown"
    : componentKeys.length > 1 || mixedAggregate ? "incompatible"
    : "compatible";
  const idsFor = (key: string) => rows.filter((_, index) => ids[index].key === key).map(row => row.id);
  if (compatibility === "compatible") return {
    compatibility, compatible: true, aggregateRows,
    populations: [{ key: "all", label: "All published rows", sport: ids[0]?.sport, rowCount: rows.length, rowIds: rows.map(row => row.id), compatibility }],
    reason: "Published rows resolve to one population.",
  };
  const populations: ResearchPopulation[] = componentKeys.map(key => {
    const member = ids.find(identity => identity.key === key)!;
    return {
      key, label: member.label, sport: member.sport,
      rowCount: components.filter(identity => identity.key === key).length,
      rowIds: idsFor(key), compatibility: "compatible" as const,
    };
  });
  if (incomplete) populations.push({
    key: UNKNOWN_POPULATION_KEY, label: UNKNOWN_POPULATION_LABEL,
    rowCount: ids.filter(identity => !identity.known).length,
    rowIds: idsFor(UNKNOWN_POPULATION_KEY), compatibility: "unknown",
  });
  const sports = new Set(components.map(identity => identity.sport).filter(Boolean));
  const partitions = new Set(components.map(identity => identity.partition || ""));
  return {
    compatibility, compatible: false, populations, aggregateRows,
    reason: compatibility === "unknown" ? analysis?.populationDefinition?.reason || "One or more published rows do not identify a population, so compatibility is unknown."
      : mixedAggregate ? "Whole-corpus estimates and their component phases are not comparable in one ranking."
      : sports.size > 1 ? "Rows describe different sports and are not comparable in one ranking."
      : partitions.size > 1 ? "Rows come from different published partitions and are not comparable in one ranking."
      : "Rows describe different populations and are not comparable in one ranking.",
  };
}
