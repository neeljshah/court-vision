// Row-level population identity for the published research analyses.
//
// Two rows may only be pooled (ranked, summarised, positioned) when both resolve
// to the SAME identity. An identity is read from the row's own published fields
// first, then from the analysis definition. A row whose identity cannot be read
// stays unknown -- it is never treated as compatible by default.
import type { ResearchPopulationDefinition, ResearchRow } from "./researchTypes";

export type ResearchRowPopulation = {
  key: string;
  label: string;
  sport?: string;
  partition?: string;
  aggregate: boolean;
  known: boolean;
};
export type ResearchPopulationContext = { sport?: string; populationDefinition?: ResearchPopulationDefinition };

export const UNKNOWN_POPULATION_KEY = "missing-definition";
export const UNKNOWN_POPULATION_LABEL = "Population not published";
const SPORT_LABELS: Record<string, string> = { soccer_intl: "International soccer", basketball_nba: "Basketball NBA" };
// Longest first: "soccer_intl" has to win before "soccer" can match inside it.
const SPORT_TOKENS = ["basketball_nba", "soccer_intl", "wnba", "nba", "mlb", "nhl", "soccer", "tennis"];

export const researchSportLabel = (sport: string) => SPORT_LABELS[sport] || sport.toUpperCase();

type Identity = { sport?: string; partition?: string; phase?: string; known: boolean };
const UNKNOWN: Identity = { known: false };

function fromPath(path: string): Identity | null {
  const grain = path.match(/(?:^|\.)sports\.([^.[\]]+)\.grains\.([^.[\]]+)/);
  if (grain) return { partition: "sports", sport: grain[1], phase: grain[2], known: true };
  const keyed = path.match(/(?:^|\.)(sports|checkpoints)\.([^.[\]]+)/);
  if (keyed) return { partition: keyed[1], sport: keyed[2], known: true };
  const bySport = path.match(/^by_sport\.([^.[\]]+)/);
  if (bySport) return { partition: "by_sport", sport: bySport[1], known: true };
  const partition = path.match(/^(by_[a-z0-9_]+)\./);
  return partition ? { partition: partition[1], known: true } : null;
}

// ponytail: last resort -- the sport a cross-sport row prints in its own group or
// label. Single-sport analyses never reach this scan; they inherit their sport.
function sportFromText(row: ResearchRow): string | undefined {
  const text = `${row.group} ${row.label}`.toLowerCase();
  return SPORT_TOKENS.find(token => new RegExp(`(?<![a-z0-9])${token}(?![a-z0-9])`).test(text));
}

export function researchRowIdentity(row: ResearchRow, context?: ResearchPopulationContext): Identity {
  if (context?.populationDefinition?.status === "unpublished") return UNKNOWN;
  const paths = row.sourcePaths || [];
  const found = paths.map(fromPath).filter((value): value is Identity => value !== null);
  if (found.length) {
    const distinct = new Set(found.map(value => `${value.partition}|${value.sport}|${value.phase}`));
    return found.length === paths.length && distinct.size === 1 ? found[0] : UNKNOWN;
  }
  if (context?.sport && context.sport !== "all") return { sport: context.sport, known: true };
  const sport = sportFromText(row);
  return sport ? { sport, known: true } : UNKNOWN;
}

function identityKey(identity: Identity, withPartition: boolean) {
  if (!identity.known) return UNKNOWN_POPULATION_KEY;
  const parts: string[] = [];
  if (withPartition) parts.push(`partition=${identity.partition || "none"}`);
  if (identity.sport) parts.push(`sport=${identity.sport}`);
  return parts.join("|") || "published";
}

function identityLabel(identity: Identity, groups: Set<string>) {
  if (!identity.known) return UNKNOWN_POPULATION_LABEL;
  if (identity.sport) return researchSportLabel(identity.sport);
  if (groups.size === 1) return [...groups][0];
  const partition = identity.partition || "";
  return partition.startsWith("by_") ? `By ${partition.slice(3).replace(/_/g, " ")}` : partition || "Published rows";
}

export function researchPopulationIds(rows: ResearchRow[], context?: ResearchPopulationContext): ResearchRowPopulation[] {
  const identities = rows.map(row => researchRowIdentity(row, context));
  const partitions = new Set(identities.filter(identity => identity.known).map(identity => identity.partition || ""));
  const keys = identities.map(identity => identityKey(identity, partitions.size > 1));
  const groupsByKey = new Map<string, Set<string>>();
  keys.forEach((key, index) => groupsByKey.set(key, (groupsByKey.get(key) || new Set()).add(rows[index].group)));
  return identities.map((identity, index) => ({
    key: keys[index],
    label: identityLabel(identity, groupsByKey.get(keys[index]) || new Set()),
    sport: identity.sport,
    partition: identity.partition,
    aggregate: identity.phase === "all",
    known: identity.known,
  }));
}
