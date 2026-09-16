import { analysisDestinations } from "./analysisDestinations";
import receipt from "../../public/data/audits/mlb-ingame-integrity.json";
import regeneration from "../../public/data/audits/mlb-ingame-regeneration.json";

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

const exposedArtifacts = receipt.exposed_artifacts;
const timingArtifacts = receipt.timing_artifacts_under_review;

/** Registry shape checked against the versioned incident receipt. */
export const integrityRegistrySummary = {
  receiptId: "mlb-ingame-integrity",
  regenerationReceiptId: "mlb-ingame-regeneration",
  measuredOn: receipt.measured_on,
  revisionPublished: regeneration.revision_published,
  exposedArtifacts,
  timingArtifacts,
  perSport: receipt.per_sport,
} as const;

const regeneratedNotice: DataIntegrityNotice = {
  id: "mlb-ingame-regenerated",
  title: "MLB in-game corpus integrity",
  measuredOn: regeneration.measured_on,
  summary: "These MLB/soccer numbers are revision 2, computed on the segment-clean corpus (2026-09-16). Revision 1 values are withdrawn and kept in the regeneration receipt.",
  affectedModules: exposedArtifacts,
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

export const dataIntegrityNotices: readonly DataIntegrityNotice[] = [regeneratedNotice, reviewNotice];

/** Returns the published integrity state for one artifact and corpus sport. */
export function status(moduleId: string, sport: IntegritySport): IntegrityStatus {
  if (sport !== "mlb" && sport !== "soccer_intl") return "clear";
  if (exposedArtifacts.includes(moduleId)) return "regenerated";
  if (timingArtifacts.includes(moduleId)) return "under-review";
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
