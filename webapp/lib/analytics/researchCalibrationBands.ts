import { field as f, snapshot } from "./labHelpers";
import { entityName } from "./comparisonData";
import { CALIBRATION_REFERENCES, calibrationCards, calibrationDate, calibrationFloors, calibrationSport, finite, type CalibrationManifest } from "./researchCalibrationCheckpoints";
import type { ResearchAnalysis, ResearchRow } from "./researchTypes";

const KEYS = ["mean_y_overall", "band_reference", "n", "n_time_buckets_with_data"];

export function buildCalibrationBandResearch(manifest: CalibrationManifest): ResearchAnalysis {
  const cards = calibrationCards(manifest, "prob_band");
  const rows: ResearchRow[] = cards.map(({ slug, entry, index }) => {
    const values = entry.key_numbers || {};
    return {
      id: `calibration-band-${slug}`,
      label: `${calibrationSport(entry) || "Published"} | ${entityName(entry)}`,
      group: calibrationSport(entry) || "Published bands",
      values: Object.fromEntries(KEYS.map((key) => [key, finite(values[key]) ? values[key] : null])),
      note: typeof entry.floors === "string" ? entry.floors : undefined,
      href: `/analytics/players/calibration/${slug}`,
      sourcePaths: KEYS.map((key) => `entries[${index}].key_numbers.${key}`),
    };
  });
  return {
    id: "calibration-by-probability-band",
    title: "Calibration by published probability band",
    sport: "all",
    category: "Calibration diagnostics",
    source: "atlas_calibration_manifest",
    question: "What does each published probability-band card record, and how much published support stands behind it?",
    method: "Restates each published probability-band card. No value is recalculated, no band is pooled across sports, and the published band reference is kept apart from the observed outcome rate.",
    description: "Published observed outcome rates, band references, and support counts by sport and probability band.",
    scope: `${rows.length} published sport-by-band rows; each row keeps its own published row count and time-bucket count.`,
    caveat: calibrationFloors(cards) || "The published manifest does not state a shared floor for these bands.",
    status: "Descriptive calibration subset",
    fields: [
      f("mean_y_overall", "Observed outcome rate", "number", 4),
      f("band_reference", "Published band reference", "number", 4),
      f("n", "Published rows", "number", 0),
      f("n_time_buckets_with_data", "Time buckets with published rows", "number", 0),
    ],
    rows,
    formula: "Published band card values restated as published: observed outcome rate, band reference, row count, and the count of time buckets with published rows.",
    interpretation: "The band reference is the published label of the band, not a mean probability produced by a model or a market. Read it beside the observed outcome rate within one sport only, and open the card for the published by_time_bucket rows behind each band.",
    references: CALIBRATION_REFERENCES,
    novelty: "Derived analysis",
    asOf: calibrationDate(cards),
  };
}

export function getCalibrationBandResearch(): ResearchAnalysis[] {
  return [buildCalibrationBandResearch(snapshot<CalibrationManifest>("atlas_calibration_manifest"))];
}
