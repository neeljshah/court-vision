import { status, type IntegritySport } from "@/lib/analytics/dataIntegrity";
import type { ArtifactReference, IngameIntegrityReceipt, IngameRegenerationReceipt, IngameTimingRegenerationReceipt } from "./ingameJoinIntegrity.server";

const sportLabels: Record<IntegritySport, string> = {
  nba: "NBA", mlb: "MLB", soccer_intl: "International soccer", tennis: "Tennis",
};

function number(value: number): string {
  return value.toLocaleString("en-US");
}

export function buildIngameJoinIntegrityFinding(
  receipt: IngameIntegrityReceipt,
  regeneration: IngameRegenerationReceipt,
  timing: IngameTimingRegenerationReceipt,
  resolveArtifact: (id: string) => ArtifactReference,
) {
  const mlb = receipt.per_sport.mlb;
  const soccer = receipt.per_sport.soccer_intl;
  const derivedUnderReview = receipt.derived_artifacts_under_review.map(entry => ({
    ...entry,
    artifact: resolveArtifact(entry.artifact),
    staleInput: resolveArtifact(entry.stale_inputs),
  }));
  const reviewedArtifacts = [...receipt.exposed_artifacts, ...receipt.timing_artifacts_regenerated, ...receipt.timing_artifacts_under_review, ...receipt.derived_artifacts_under_review.map(entry => entry.artifact)];
  const statusRows = reviewedArtifacts.flatMap((artifact) => (["mlb", "soccer_intl"] as IntegritySport[])
    .map(sportId => ({ artifact: resolveArtifact(artifact), sport: sportLabels[sportId], state: status(artifact, sportId) }))
    .filter(row => row.state !== "clear"));
  return {
    measuredOn: receipt.measured_on,
    method: receipt.method,
    counts: [
      { sport: "MLB", files: number(mlb.files), ticks: number(mlb.ticks), mixedFiles: number(mlb.mixed_files), mismatchedTicks: number(mlb.mismatched_ticks || 0), statelessTicks: number(mlb.stateless_ticks), truncatedGames: number(mlb.truncated_games), disagreements: number(mlb.label_disagreements) },
      { sport: "International soccer", files: number(soccer.files), ticks: number(soccer.ticks), mixedFiles: number(soccer.mixed_files), mismatchedTicks: "Not reported", statelessTicks: number(soccer.stateless_ticks), truncatedGames: number(soccer.truncated_games), disagreements: `${number(soccer.label_disagreements)} (${soccer.label_disagreement_note})` },
    ],
    agreement: [
      { population: "Late-inning (inning 7+) leading-side labels across all MLB ticks", frequency: mlb.late_inning_leader_agreement?.all_ticks.frequency || 0, n: mlb.late_inning_leader_agreement?.all_ticks.n || 0 },
      { population: "Late-inning (inning 7+) leading-side labels in the final MLB segment", frequency: mlb.late_inning_leader_agreement?.final_segment.frequency || 0, n: mlb.late_inning_leader_agreement?.final_segment.n || 0 },
    ],
    leaderAgreement: `Game-level labels agree with the last stated score in all ${number(mlb.leader_wins_last_tick?.games || 0)} games with a leader (frequency ${(mlb.leader_wins_last_tick?.frequency || 0).toFixed(4)}).`,
    exposedArtifacts: receipt.exposed_artifacts.map(resolveArtifact),
    timingArtifacts: receipt.timing_artifacts_under_review.map(resolveArtifact),
    timingRegeneratedArtifacts: receipt.timing_artifacts_regenerated.map(resolveArtifact),
    timingNote: receipt.timing_artifacts_note,
    statusRows,
    derivedUnderReview,
    regeneration: {
      measuredOn: regeneration.measured_on,
      revision: regeneration.revision_published,
      method: regeneration.method.summary,
      corpus: regeneration.method.corpus_after,
      checkerVerdict: regeneration.checker.verdict,
      reading: regeneration.reading,
      rows: regeneration.artifacts.map(row => ({
        artifact: resolveArtifact(row.artifact),
        population: row.n_field,
        nBefore: number(row.n_before),
        nAfter: number(row.n_after),
        headlineBefore: row.headline_before,
        headlineAfter: row.headline_after,
      })),
    },
    timingRegeneration: {
      measuredOn: timing.measured_on,
      revision: timing.revision_published,
      method: timing.method.summary,
      overrideEnv: timing.method.override_env,
      corpus: timing.method.corpus_after,
      checkerVerdict: timing.checker.verdict,
      reading: timing.reading,
      rows: timing.artifacts.map(row => ({
        artifact: resolveArtifact(row.artifact),
        population: row.n_field,
        nBefore: number(row.n_before),
        nAfter: number(row.n_after),
        headlineBefore: row.headline_before,
        headlineAfter: row.headline_after,
      })),
    },
  };
}
