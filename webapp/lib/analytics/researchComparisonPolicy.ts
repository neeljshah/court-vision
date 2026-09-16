import type { ResearchRow } from "./researchTypes";

export type ResearchCompatibility = "compatible" | "incompatible" | "unknown";
export type ResearchPopulation = {
  key: string;
  label: string;
  sport?: string;
  rowCount: number;
  compatibility: ResearchCompatibility;
};
export type ResearchComparisonPolicy = {
  compatibility: ResearchCompatibility;
  compatible: boolean;
  populations: ResearchPopulation[];
  aggregateRows: ResearchRow[];
  reason: string;
};

type PublishedPopulation = { sport?: string; phase?: string; aggregate: boolean; known: boolean };
const sportLabels: Record<string, string> = { soccer_intl: "International soccer" };
const label = (sport: string) => sportLabels[sport] || sport.toUpperCase();

function publishedPopulation(row: ResearchRow): PublishedPopulation {
  const paths = row.sourcePaths || [];
  const found = paths.map(path => {
    const grains = path.match(/(?:^|\.)sports\.([^.[\]]+)\.grains\.([^.[\]]+)/);
    if (grains) return { sport: grains[1], phase: grains[2] };
    const sport = path.match(/(?:^|\.)(?:sports|checkpoints)\.([^.[\]]+)/);
    return sport ? { sport: sport[1] } : null;
  }).filter((value): value is { sport: string; phase?: string } => value !== null);
  if (!found.length) return { aggregate: false, known: false };
  const sports = new Set(found.map(value => value.sport));
  const phases = new Set(found.map(value => value.phase).filter((value): value is string => Boolean(value)));
  if (sports.size !== 1 || phases.size > 1) return { aggregate: false, known: false };
  const sport = found[0].sport, phase = phases.values().next().value as string | undefined;
  return { sport, phase, aggregate: phase === "all", known: !found.some(value => value.phase !== undefined) || Boolean(phase) };
}

export function matchesResearchPopulation(row: ResearchRow, population: ResearchPopulation) {
  return publishedPopulation(row).sport === population.sport;
}

export function researchComparisonPolicy(rows: ResearchRow[]): ResearchComparisonPolicy {
  const definitions = rows.map(row => ({ row, population: publishedPopulation(row) }));
  const carriesPopulation = definitions.some(({ population }) => population.known);
  if (!carriesPopulation) return {
    compatibility: "compatible", compatible: true,
    populations: [{ key: "all", label: "All published rows", rowCount: rows.length, compatibility: "compatible" }],
    aggregateRows: [], reason: "Published rows do not expose sport populations.",
  };
  const incomplete = definitions.some(({ population }) => !population.known);
  const aggregateRows = definitions.filter(({ population }) => population.aggregate).map(({ row }) => row);
  const components = definitions.filter(({ population }) => !population.aggregate && population.known);
  const sports = new Set(components.map(({ population }) => population.sport));
  const mixedAggregate = aggregateRows.length > 0 && components.length > 0;
  const compatibility: ResearchCompatibility = incomplete ? "unknown" : sports.size > 1 || mixedAggregate ? "incompatible" : "compatible";
  const populations: ResearchPopulation[] = [...sports].filter((sport): sport is string => Boolean(sport)).map(sport => ({
    key: `sport=${sport}`, label: label(sport), sport,
    rowCount: components.filter(({ population }) => population.sport === sport).length,
    compatibility: "compatible" as const,
  }));
  if (incomplete) populations.push({ key: "missing-definition", label: "Definition not published", rowCount: definitions.filter(({ population }) => !population.known).length, compatibility: "unknown" });
  return {
    compatibility, compatible: compatibility === "compatible", populations, aggregateRows,
    reason: compatibility === "compatible" ? "Published sport populations are consistent across these rows."
      : compatibility === "unknown" ? "One or more published rows omit a required sport or phase field, so compatibility is unknown."
      : mixedAggregate ? "Whole-corpus estimates and their component phases are not comparable in one ranking."
      : "Rows describe different sports and are not comparable in one ranking.",
  };
}
