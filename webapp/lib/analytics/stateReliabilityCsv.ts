"use client";

import { stateReliabilityMetricValue, type StateReliabilityRow, type StateReliabilitySport } from "./stateReliability";

const sourceArtifact = "public/data/showcase/state_conditioned_calibration.json";
const caveat = "forecast observations, not independent games; unpaired source populations; observation dates not published; absent cells omitted";
const headers = [
  "sport", "source", "time_bucket", "probability_bucket", "n (forecast observations)",
  "mean_p (probability)", "mean_y (observed frequency)", "calibration_error (probability)",
  "signed_gap_pp (percentage points)", "absolute_gap_pp (percentage points)",
  "artifact_date", "observation_window", "source_artifact", "caveat",
];

function textCell(value: string): string {
  return `"${(/^\s*[=+@-]|^[\t\r\n]/.test(value) ? "'" + value : value).replace(/"/g, '""')}"`;
}

function numberCell(value: number): string {
  return Number.isFinite(value) ? String(value) : "";
}

export function buildStateReliabilityCSV(sport: StateReliabilitySport, rows: StateReliabilityRow[]): string {
  return [headers.map(textCell).join(","), ...rows.map(row => [
    textCell(row.sport), textCell(row.source), textCell(row.timeBucket), textCell(row.probabilityBucket),
    numberCell(row.n), numberCell(row.meanP), numberCell(row.meanY), numberCell(row.calibrationError),
    numberCell(stateReliabilityMetricValue(row, "signed-gap")), numberCell(stateReliabilityMetricValue(row, "absolute-gap")),
    textCell(sport.artifactDate || ""), textCell(""), textCell(sourceArtifact), textCell(caveat),
  ].join(","))].join("\r\n");
}

export function exportStateReliabilityCSV(sport: StateReliabilitySport, rows: StateReliabilityRow[]): void {
  const url = URL.createObjectURL(new Blob([buildStateReliabilityCSV(sport, rows)], { type: "text/csv;charset=utf-8" }));
  const anchor = document.createElement("a");
  const safeSport = sport.sport.toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "") || "unknown";
  anchor.href = url;
  anchor.download = `courtvision-state-reliability-${safeSport}.csv`;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
