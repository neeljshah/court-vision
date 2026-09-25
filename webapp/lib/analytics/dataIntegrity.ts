import { analysisDestinations } from "./analysisDestinations";
import receipt from "../../public/data/audits/mlb-ingame-integrity.json";
import regeneration from "../../public/data/audits/mlb-ingame-regeneration.json";
import timingRegeneration from "../../public/data/audits/mlb-ingame-timing-regeneration.json";

export type IntegritySport = "nba" | "mlb" | "soccer_intl" | "tennis";
export type IntegrityStatus = "clear" | "regenerated" | "under-review";

export type DataIntegrityNotice = {
  id: string;
  title: string;
  measuredOn: string;
  summary: string;
  affectedModules: readonly string[];
  status: Exclude<IntegrityStatus, "clear">;
  detailRoute: string;
};

const exposedArtifacts: readonly string[] = receipt.exposed_artifacts;
// Empty once every timing artifact is regenerated; the key stays so a future defect has a home.
const timingArtifacts: readonly string[] = receipt.timing_artifacts_under_review;
const timingRegeneratedArtifacts: readonly string[] = receipt.timing_artifacts_regenerated;
// Artifacts composed from a rebuilt input that still carry revision 1 numbers.
const derivedArtifactsUnderReview = receipt.derived_artifacts_under_review;

function count(value: number): string {
  return value.toLocaleString("en-US");
}
function share(part: number, whole: number): string {
  return `${((part / whole) * 100).toFixed(1)} percent`;
}

/**
 * The two MLB shares, derived from the receipts so they cannot drift apart.
 * excluded is every tick segmentation dropped; mismatched is the smaller,
 * specifically identified label-mismatch count. Conflating them overstates one
 * and understates the other.
 */
export const mlbTickShares = (() => {
  const segmentation = regeneration.segmentation.per_sport.mlb;
  const ticksIn = segmentation.ticks_in;
  const excluded = ticksIn - segmentation.ticks_kept;
  const mismatched = receipt.per_sport.mlb.mismatched_ticks;
  return {
    ticksIn,
    excluded,
    mismatched,
    sentence: `Segmentation excluded ${count(excluded)} of the ${count(ticksIn)} MLB ticks (${share(excluded, ticksIn)}); the specifically identified label mismatches were a smaller ${count(mismatched)} (${share(mismatched, ticksIn)}).`,
  };
})();

/** Registry shape checked against the versioned incident receipt. */
export const integrityRegistrySummary = {
  receiptId: "mlb-ingame-integrity",
  regenerationReceiptId: "mlb-ingame-regeneration",
  timingRegenerationReceiptId: "mlb-ingame-timing-regeneration",
  measuredOn: receipt.measured_on,
  revisionPublished: regeneration.revision_published,
  timingMeasuredOn: timingRegeneration.measured_on,
  exposedArtifacts,
  timingArtifacts,
  timingRegeneratedArtifacts,
  derivedArtifactsUnderReview,
  perSport: receipt.per_sport,
} as const;

const regeneratedNotice: DataIntegrityNotice = {
  id: "mlb-ingame-regenerated",
  title: "MLB in-game corpus integrity",
  measuredOn: regeneration.measured_on,
  summary: `These MLB/soccer numbers are revision 2, computed on the segment-clean corpus (2026-09-16). Revision 1 values are withdrawn and kept in the regeneration receipt. ${mlbTickShares.sentence}`,
  affectedModules: exposedArtifacts,
  status: "regenerated",
  detailRoute: "/analytics/findings/ingame-join-integrity/",
};

const timingRegeneratedNotice: DataIntegrityNotice = {
  id: "ingame-timing-regenerated",
  title: "In-game timing artifacts regenerated",
  measuredOn: timingRegeneration.measured_on,
  summary: `This timing measurement is revision ${timingRegeneration.revision_published}, rebuilt on the segment-clean corpus (${timingRegeneration.measured_on}). The stored corpus contains ${count(timingRegeneration.checker.segmented.mlb_segmented.games)} MLB and ${count(timingRegeneration.checker.segmented.soccer_intl_segmented.games)} international soccer games. Individual measurements can use fewer games after eligibility checks; read their own denominators. Revision 1 values are withdrawn and kept in the timing regeneration receipt.`,
  affectedModules: timingRegeneratedArtifacts,
  status: "regenerated",
  detailRoute: "/analytics/findings/ingame-join-integrity/",
};

const reviewNotice: DataIntegrityNotice = {
  id: "ingame-timing-review",
  title: "In-game corpus integrity review",
  measuredOn: integrityRegistrySummary.measuredOn,
  summary: "This artifact's MLB/soccer rows are under review: it was not regenerated in this pass, and mixed-game tick paths may distort timing measurements.",
  affectedModules: timingArtifacts,
  status: "under-review",
  detailRoute: "/analytics/findings/ingame-join-integrity/",
};

const derivedReviewNotices: DataIntegrityNotice[] = derivedArtifactsUnderReview.map(entry => ({
  id: `derived-review-${entry.artifact.replace(/_/g, "-")}`,
  title: "Composed artifact awaiting recomposition",
  measuredOn: integrityRegistrySummary.measuredOn,
  summary: `${entry.note} Stale input: ${entry.stale_inputs}.`,
  affectedModules: [entry.artifact],
  status: "under-review",
  detailRoute: "/analytics/findings/ingame-join-integrity/",
}));

export const dataIntegrityNotices: readonly DataIntegrityNotice[] = [regeneratedNotice, timingRegeneratedNotice, reviewNotice, ...derivedReviewNotices];

/** Returns the published integrity state for one artifact and corpus sport. */
export function status(moduleId: string, sport: IntegritySport): IntegrityStatus {
  if (sport !== "mlb" && sport !== "soccer_intl") return "clear";
  if (exposedArtifacts.includes(moduleId)) return "regenerated";
  if (timingRegeneratedArtifacts.includes(moduleId)) return "regenerated";
  if (timingArtifacts.includes(moduleId)) return "under-review";
  if (derivedArtifactsUnderReview.some(entry => entry.artifact === moduleId)) return "under-review";
  return "clear";
}

export const integrityStatus = status;

export function noticesForModules(ids: readonly string[]): DataIntegrityNotice[] {
  const requested = new Set(ids);
  return dataIntegrityNotices.filter(notice => notice.affectedModules.some(id => requested.has(id)));
}

export function noticesForPaper(evidence: ReadonlyArray<{ module: string }>): DataIntegrityNotice[] {
  return noticesForModules(evidence.map(entry => entry.module));
}

export function noticesForInspector(destinationId: string): DataIntegrityNotice[] {
  const destination = analysisDestinations.find(entry => entry.id === destinationId);
  return destination ? noticesForModules(destination.sourceModuleIds) : [];
}
