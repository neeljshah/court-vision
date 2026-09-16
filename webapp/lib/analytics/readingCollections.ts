import type { LibraryEntry } from "./libraryTypes";
import { analysisDestinations } from "./analysisDestinations";

export type CollectionMemberKind = "analysis" | "finding" | "inspector" | "module";
export type CollectionMember = { id: string; kind: CollectionMemberKind };
export type ReadingCollection = {
  id: string;
  title: string;
  description: string;
  members: CollectionMember[];
};

// These are editorial routes, not a second registry. Validation below keeps every
// hand-picked member attached to a public library entry.
export const readingCollections: ReadingCollection[] = [
  {
    id: "forecast-calibration",
    title: "How calibrated are the forecasts?",
    description: "Read the reliability checks, game checkpoints, and probability-score comparisons together.",
    members: [
      { kind: "analysis", id: "calibration-by-game-checkpoint" },
      { kind: "analysis", id: "brier-skill-score-by-game-phase" },
      { kind: "analysis", id: "brier-relative-gap" },
      { kind: "module", id: "murphy_decomposition" },
      { kind: "finding", id: "reliability" },
      { kind: "inspector", id: "calibration" },
      { kind: "inspector", id: "state-reliability" },
      { kind: "inspector", id: "score-decomposition" },
      { kind: "inspector", id: "cross-sport-comparability" },
    ],
  },
  {
    id: "data-independence",
    title: "How much data is really there?",
    description: "Separate raw row counts from repeated observations, effective support, and interval width.",
    members: [
      { kind: "module", id: "ess_ledger" },
      { kind: "analysis", id: "cluster-interval-width" },
      { kind: "analysis", id: "calibration-support-concentration" },
      { kind: "finding", id: "effective-sample-size" },
      { kind: "inspector", id: "observation-dependence" },
      { kind: "inspector", id: "residual-anatomy" },
    ],
  },
  {
    id: "within-game-change",
    title: "What changes inside a game?",
    description: "Follow score-state, fourth-quarter, and information-arrival measurements through a game.",
    members: [
      { kind: "analysis", id: "comeback-rates-deficit-time" },
      { kind: "module", id: "blowout_dynamics" },
      { kind: "analysis", id: "nba-q4-role-redistribution" },
      { kind: "analysis", id: "information-arrival-brier-by-checkpoint" },
      { kind: "analysis", id: "market-convergence-by-checkpoint" },
      { kind: "inspector", id: "blowout-timing" },
      { kind: "inspector", id: "state-contrasts" },
    ],
  },
  {
    id: "mlb-pitch-context",
    title: "How do pitch types change by count?",
    description: "Read the pitch-type distribution, count states, and next-pitch transitions together.",
    members: [
      { kind: "analysis", id: "mlb-velocity-shape" },
      { kind: "analysis", id: "mlb-pitch-mix-concentration" },
      { kind: "analysis", id: "mlb-count-contrast" },
      { kind: "inspector", id: "pitch-sequencing" },
      { kind: "inspector", id: "count-context" },
    ],
  },
  {
    id: "players-and-teams",
    title: "Who are the players and teams?",
    description: "Start with atlas measurements, then inspect player context, on-off rows, and lineup support.",
    members: [
      { kind: "analysis", id: "nba-player-atlas-measurements" },
      { kind: "analysis", id: "nba-team-atlas-measurements" },
      { kind: "analysis", id: "nba-player-context-consistency-q4-venue-onoff" },
      { kind: "analysis", id: "nba-on-off-net-rating-by-player" },
      { kind: "analysis", id: "nba-lineup-expectation-reversals" },
      { kind: "analysis", id: "nba-variability-imbalance" },
    ],
  },
  {
    id: "market-knowledge",
    title: "What does the market know?",
    description: "Compare observed disagreement, convergence, devigged movement, calibration, and source accuracy.",
    members: [
      { kind: "analysis", id: "market-disagreement-brier-by-bucket" },
      { kind: "analysis", id: "market-convergence-by-checkpoint" },
      { kind: "analysis", id: "devigged-movement-by-time-to-close" },
    ],
  },
];

export function collectionMemberIds(id: string): string[] {
  return readingCollections.find((collection) => collection.id === id)?.members.map((member) => member.id) || [];
}

// ponytail: finding slugs are passed in so this module stays free of node:fs (findingsIndex reads the snapshot)
export function validateReadingCollections(entries: Pick<LibraryEntry, "id">[], findingSlugs: readonly string[] = []): string[] {
  const entryIds = new Set([
    ...entries.map((entry) => entry.id),
    ...findingSlugs,
    ...analysisDestinations.map((destination) => destination.id),
  ]);
  return readingCollections.flatMap((collection) => collection.members.flatMap((member) =>
    entryIds.has(member.id) ? [] : [`${collection.id}: ${member.kind}/${member.id}`]
  ));
}
