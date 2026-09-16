import { analysisDestinations } from "./analysisDestinations";

export type IntegrityExposure = "label-contamination" | "truncation";
export type IntegrityStatus = "pending-regeneration";

export type DataIntegrityNotice = {
  id: string;
  title: string;
  measuredOn: string;
  summary: string;
  affectedModules: readonly string[];
  exposure: IntegrityExposure;
  status: IntegrityStatus;
  detailRoute: string;
};

const MLB_INGAME_JOIN_INTEGRITY: DataIntegrityNotice = {
  id: "mlb-ingame-join-integrity",
  title: "MLB in-game corpus join integrity",
  measuredOn: "2026-09-16",
  summary: "Measured 2026-09-16: 126 of 227 MLB game files contain ticks from more than one real game; 27,076 of 78,986 ticks (34.3 percent) sit in a pre-final segment carrying another game's label. In addition, 26,340 of 78,986 ticks (33.3 percent) carry no game state, and 61 of 227 games have no leader at the last stated tick. The listed MLB calibration artifacts are pending regeneration from a segment-clean corpus; until then their numbers are measured on a partly mislabelled tick set.",
  affectedModules: [
    "state_conditioned_calibration", "calibration_stability", "murphy_decomposition",
    "brier_skill_scores", "residual_anatomy", "calibration_by_market_type",
    "residual_autocorrelation", "calibration_over_time", "calibration_atlas",
    "market_disagreement_profile", "info_arrival_curve", "market_overreaction",
    "soccer_calibration_pack",
  ],
  exposure: "label-contamination",
  status: "pending-regeneration",
  detailRoute: "/analytics/findings/ingame-join-integrity/",
};

export const dataIntegrityNotices: readonly DataIntegrityNotice[] = [MLB_INGAME_JOIN_INTEGRITY];

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
