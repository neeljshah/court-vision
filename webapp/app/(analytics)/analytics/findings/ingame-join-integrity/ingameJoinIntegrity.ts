import { status, type IntegritySport } from "@/lib/analytics/dataIntegrity";
import type { IngameIntegrityReceipt } from "./ingameJoinIntegrity.server";

const sportLabels: Record<IntegritySport, string> = {
  nba: "NBA", mlb: "MLB", soccer_intl: "International soccer", tennis: "Tennis",
};

function number(value: number): string {
  return value.toLocaleString("en-US");
}

export function buildIngameJoinIntegrityFinding(receipt: IngameIntegrityReceipt) {
  const mlb = receipt.per_sport.mlb;
  const soccer = receipt.per_sport.soccer_intl;
  const reviewedArtifacts = [...receipt.exposed_artifacts, ...receipt.timing_artifacts_under_review];
  const statusRows = reviewedArtifacts.flatMap((artifact) => (["mlb", "soccer_intl"] as IntegritySport[])
    .map(sportId => ({ artifact, sport: sportLabels[sportId], state: status(artifact, sportId) }))
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
    exposedArtifacts: receipt.exposed_artifacts,
    timingArtifacts: receipt.timing_artifacts_under_review,
    timingNote: receipt.timing_artifacts_note,
    statusRows,
  };
}
