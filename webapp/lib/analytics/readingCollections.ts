import type { Finding } from "./findingsIndex";
import type { ResearchAnalysis } from "./researchTypes";

export type CollectionMemberKind = "analysis" | "finding" | "module";
export type CollectionMember = { id: string; kind: CollectionMemberKind };
export type ReadingCollection = {
  id: string;
  title: string;
  description: string;
  members: CollectionMember[];
};

// These are editorial routes, not a second registry. Validation below keeps every
// hand-picked member attached to a public research analysis, finding, or module.
export const readingCollections: ReadingCollection[] = [
  {
    id: "forecast-calibration",
    title: "How calibrated are the forecasts?",
    description: "Read the reliability checks, game checkpoints, and probability-score comparisons together.",
    members: [
      { kind: "analysis", id: "calibration-by-game-checkpoint" },
      { kind: "finding", id: "reliability" },
      { kind: "analysis", id: "brier-skill-score-by-game-phase" },
      { kind: "analysis", id: "brier-relative-gap" },
      { kind: "module", id: "murphy_decomposition" },
    ],
  },
  {
    id: "data-independence",
    title: "How much data is really there?",
    description: "Separate raw row counts from repeated observations, effective support, and interval width.",
    members: [
      { kind: "finding", id: "effective-sample-size" },
      { kind: "module", id: "ess_ledger" },
      { kind: "analysis", id: "cluster-interval-width" },
      { kind: "analysis", id: "calibration-support-concentration" },
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
      { kind: "finding", id: "forecast-life" },
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
      { kind: "finding", id: "favorite-longshot" },
      { kind: "finding", id: "bookmaker-accuracy" },
      { kind: "analysis", id: "devigged-movement-by-time-to-close" },
    ],
  },
];

export function collectionMemberIds(id: string): string[] {
  return readingCollections.find((collection) => collection.id === id)?.members.map((member) => member.id) || [];
}

export function validateReadingCollections(
  analyses: Pick<ResearchAnalysis, "id">[],
  findings: Pick<Finding, "slug">[],
  moduleIds: string[],
): string[] {
  const analysisIds = new Set(analyses.map((analysis) => analysis.id));
  const findingIds = new Set(findings.map((finding) => finding.slug));
  const modules = new Set(moduleIds);
  return readingCollections.flatMap((collection) => collection.members.flatMap((member) => {
    const exists = member.kind === "analysis" ? analysisIds.has(member.id)
      : member.kind === "finding" ? findingIds.has(member.id) : modules.has(member.id);
    return exists ? [] : [`${collection.id}: ${member.kind}/${member.id}`];
  }));
}
