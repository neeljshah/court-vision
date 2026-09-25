import { describe, expect, it } from "vitest";
import { getResearchAnalyses } from "./researchData";
import { researchComparisonPolicy } from "./researchComparisonPolicy";
import { researchPopulationIds, researchRowIdentity, UNKNOWN_POPULATION_KEY } from "./researchPopulations";
import type { ResearchRow } from "./researchTypes";

const row = (id: string, group: string, label = id, sourcePaths?: string[]): ResearchRow => ({ id, label, group, values: { value: 1 }, sourcePaths });

// One population: every row resolves to the same sport and partition.
const SINGLE_POPULATION = [
  "nba-player-atlas-measurements", "nba-team-atlas-measurements", "mlb-batter-atlas-measurements",
  "tennis-player-atlas-measurements", "mlb-pitch-type-atlas-measurements", "mlb-team-pitch-atlas-measurements", "mlb-count-state-atlas-measurements",
  "mlb-batter-p90-minus-mean-exit-velocity", "nba-opponent-total-range", "tennis-hard-recent-career-shift",
  "tennis-clay-recent-career-shift", "tennis-grass-recent-career-shift", "tennis-clay-gap-window-shift", "tennis-grass-gap-window-shift", "pace-variance-favorite-probability", "star-removal-team-win-probability",
  "lineup-proxy-active-missed-record", "comeback-rates-deficit-time", "nba-venue-shooting-gap", "nba-venue-box-profile",
  "nba-player-venue-dispersion", "nba-pra-role-composition", "nba-context-ts-dominant-gap", "mlb-velocity-band-concentration",
  "mlb-shrinkage-displacement", "soccer-minute-calibration-support", "tennis-surface-prior-brier-delta", "nba-on-off-net-rating-by-player",
  "mlb-catcher-out-of-zone-strike-rate", "nba-team-profile-pace-fragility-fatigue-halftime", "nba-player-context-consistency-q4-venue-onoff",
  "nba-variability-imbalance", "nba-lineup-expectation-reversals", "nba-rim-two-axis-pressure", "nba-q4-role-redistribution",
  "nba-form-endpoint-elasticity", "nba-schedule-compression-profile", "nba-matchup-profile-contrast", "mlb-velocity-shape",
  "mlb-pitch-mix-concentration", "mlb-count-contrast", "tennis-surface-support", "tennis-surface-spread", "tennis-surface-balance",
  "soccer-venue-outcome-balance", "soccer-tournament-venue-support", "soccer-form-strength-alignment",
];
// More than one population: the reader must pick one before anything is pooled.
const MULTI_POPULATION = [
  "calibration-by-game-checkpoint", "calibration-by-probability-band", "market-disagreement-brier-by-bucket",
  "information-arrival-brier-by-checkpoint", "market-convergence-by-checkpoint", "brier-skill-score-by-game-phase",
  "hypothesis-survival-by-mechanism", "devigged-movement-by-time-to-close", "brier-relative-gap", "signed-calibration-direction",
  "observed-cohort-shift", "cluster-interval-width", "calibration-support-concentration", "verdict-mix-entropy", "verdict-friction-share",
];
// No population identity is published, so nothing may be pooled at all.
const UNIDENTIFIED = ["answer-evidence-coverage", "soccer-trailing-attack-defense", "soccer-home-away-trailing-form-gap", "soccer-team-atlas-measurements", "mlb-platoon-support-balance", "tennis-clay-hard-match-support"];
// Rates whose own published explanation says they answer different questions.
const QA_RATE_ANALYSES = ["answer-evidence-coverage", "verdict-mix-entropy", "verdict-friction-share"];

const analyses = getResearchAnalyses();
const policies = new Map(analyses.map(analysis => [analysis.id, researchComparisonPolicy(analysis.rows, analysis)]));

describe("research population identity", () => {
  it("covers every published analysis exactly once", () => {
    const enumerated = [...SINGLE_POPULATION, ...MULTI_POPULATION, ...UNIDENTIFIED];
    expect(new Set(enumerated).size).toBe(enumerated.length);
    expect([...enumerated].sort()).toEqual(analyses.map(analysis => analysis.id).sort());
    expect(enumerated).toHaveLength(analyses.length);
  });

  it("pools only the analyses whose rows resolve to one population", () => {
    for (const id of SINGLE_POPULATION) expect([id, policies.get(id)?.compatibility]).toEqual([id, "compatible"]);
    for (const id of MULTI_POPULATION) {
      const policy = policies.get(id)!;
      expect([id, policy.compatibility]).toEqual([id, "incompatible"]);
      expect(policy.populations.length).toBeGreaterThan(1);
    }
    for (const id of UNIDENTIFIED) {
      const policy = policies.get(id)!;
      expect([id, policy.compatibility]).toEqual([id, "unknown"]);
      expect(policy.populations.map(population => population.key)).toEqual([UNKNOWN_POPULATION_KEY]);
    }
  });

  it("never reports compatible for a mixed-sport or mixed-partition row set", () => {
    for (const analysis of analyses) {
      const ids = researchPopulationIds(analysis.rows, analysis);
      const sports = new Set(ids.map(identity => identity.sport));
      const partitions = new Set(ids.map(identity => identity.partition));
      const mixed = sports.size > 1 || partitions.size > 1 || ids.some(identity => !identity.known);
      if (mixed) expect([analysis.id, policies.get(analysis.id)?.compatible]).toEqual([analysis.id, false]);
    }
  });

  it("keeps every QA-rate analysis out of a pooled summary", () => {
    for (const id of QA_RATE_ANALYSES) expect([id, policies.get(id)?.compatible]).toEqual([id, false]);
  });

  it("reads the sport and partition a row publishes before anything else", () => {
    expect(researchRowIdentity(row("a", "MLB", "MLB | all", ["sports.mlb.grains.all.brier_model"]), { sport: "nba" }))
      .toMatchObject({ sport: "mlb", partition: "sports", phase: "all", known: true });
    expect(researchRowIdentity(row("b", "Sport", "Nba", ["by_sport.nba.n"]))).toMatchObject({ sport: "nba", partition: "by_sport" });
    expect(researchRowIdentity(row("c", "Mechanism family", "Travel", ["by_category.travel.n"]))).toEqual({ partition: "by_category", known: true });
  });

  it("falls back to the analysis sport, then to the sport the row names, then to unknown", () => {
    expect(researchRowIdentity(row("a", "East", "Alpha"), { sport: "nba" })).toMatchObject({ sport: "nba", known: true });
    expect(researchRowIdentity(row("b", "mlb_moneyline", "MLB in-game moneyline"), { sport: "all" })).toMatchObject({ sport: "mlb", known: true });
    expect(researchRowIdentity(row("c", "SOCCER_INTL", "soccer_intl minute 0-15"), { sport: "all" })).toMatchObject({ sport: "soccer_intl", known: true });
    expect(researchRowIdentity(row("d", "Coverage stress", "Answerable stress prompts"), { sport: "all" })).toEqual({ known: false });
  });

  it("separates partitions only when the row set publishes more than one", () => {
    const oneSport = researchPopulationIds([row("a", "MLB", "MLB | 1", ["checkpoints.mlb.1.v"]), row("b", "MLB", "MLB | 2", ["checkpoints.mlb.2.v"])]);
    expect(oneSport.map(identity => identity.key)).toEqual(["sport=mlb", "sport=mlb"]);
    const twoPartitions = researchPopulationIds([row("a", "Mechanism family", "Travel", ["by_category.travel.n"]), row("b", "Sport", "Nba", ["by_sport.nba.n"])]);
    expect(twoPartitions.map(identity => identity.key)).toEqual(["partition=by_category", "partition=by_sport|sport=nba"]);
    expect(twoPartitions.map(identity => identity.label)).toEqual(["Mechanism family", "NBA"]);
  });
});
