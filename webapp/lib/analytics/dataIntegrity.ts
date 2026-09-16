import { analysisDestinations } from "./analysisDestinations";
import receipt from "../../public/data/audits/mlb-ingame-integrity.json";

export type IntegritySport = "nba" | "mlb" | "soccer_intl" | "tennis";
export type IntegrityStatus = "clear" | "withdrawn-pending-regeneration" | "under-review";

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
  measuredOn: receipt.measured_on,
  exposedArtifacts,
  timingArtifacts,
  perSport: receipt.per_sport,
} as const;

const withdrawnNotice: DataIntegrityNotice = {
  id: "mlb-ingame-withdrawal",
  title: "MLB in-game corpus integrity",
  measuredOn: integrityRegistrySummary.measuredOn,
  summary: "MLB in-game results are withdrawn pending corpus correction and regeneration. The measurements below are kept as a dated record and must not be read as current calibration quality.",
  affectedModules: exposedArtifacts,
  status: "withdrawn-pending-regeneration",
  detailRoute: "/analytics/findings/ingame-join-integrity/",
};

const reviewNotice: DataIntegrityNotice = {
  id: "ingame-timing-review",
  title: "In-game corpus integrity review",
  measuredOn: integrityRegistrySummary.measuredOn,
  summary: "This artifact's MLB/soccer rows are under review: mixed-game tick paths may distort timing measurements.",
  affectedModules: [...exposedArtifacts, ...timingArtifacts],
  status: "under-review",
  detailRoute: "/analytics/findings/ingame-join-integrity/",
};

export const dataIntegrityNotices: readonly DataIntegrityNotice[] = [withdrawnNotice, reviewNotice];

/** Returns the published integrity state for one artifact and corpus sport. */
export function status(moduleId: string, sport: IntegritySport): IntegrityStatus {
  if (sport === "mlb" && exposedArtifacts.includes(moduleId)) return "withdrawn-pending-regeneration";
  if ((sport === "mlb" || sport === "soccer_intl") && (exposedArtifacts.includes(moduleId) || timingArtifacts.includes(moduleId))) return "under-review";
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
