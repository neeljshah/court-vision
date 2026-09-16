import { field as f, snapshot } from "./labHelpers";
import { entrySlugs, entityName, type RawEntry } from "./comparisonData";
import type { ResearchAnalysis, ResearchReference, ResearchRow } from "./researchTypes";

export type CalibrationEntry = RawEntry & { sport?: unknown; card_type?: unknown };
export type CalibrationManifest = { entries?: CalibrationEntry[] };
export type CalibrationCard = { slug: string; entry: CalibrationEntry; index: number };

export const CALIBRATION_REFERENCES: ResearchReference[] = [{
  title: "Published calibration checkpoint atlas",
  url: "https://github.com/neeljshah/court-vision/blob/master/webapp/public/data/showcase/atlas_calibration_manifest.json",
}];
export const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
export const calibrationSport = (entry: CalibrationEntry) => typeof entry.sport === "string" ? entry.sport.toUpperCase() : "";

// The manifest mixes card types. Each card keeps its index in the published
// manifest so a row's source paths still point at its own entry.
export function calibrationCards(manifest: CalibrationManifest, cardType: string): CalibrationCard[] {
  return entrySlugs(manifest.entries || [])
    .map(({ slug, entry }, index) => ({ slug, entry: entry as CalibrationEntry, index }))
    .filter(card => card.entry.card_type === cardType);
}

export function calibrationFloors(cards: CalibrationCard[]): string {
  return [...new Set(cards.map(({ entry }) => entry.floors).filter((value): value is string => typeof value === "string" && value.trim().length > 0))].join(" ");
}

export function calibrationDate(cards: CalibrationCard[]): string | undefined {
  const values = cards.map(({ entry }) => typeof entry.as_of === "string" ? entry.as_of.slice(0, 10) : "");
  return values.length && values.every((value) => /^\d{4}-\d{2}-\d{2}$/.test(value)) && new Set(values).size === 1 ? values[0] : undefined;
}

export function buildCalibrationCheckpointResearch(manifest: CalibrationManifest): ResearchAnalysis {
  const cards = calibrationCards(manifest, "time_checkpoint");
  const rows: ResearchRow[] = cards.map(({ slug, entry, index }) => {
    const values = entry.key_numbers || {};
    const model = finite(values.model_ece) ? values.model_ece : null;
    const market = finite(values.market_ece) ? values.market_ece : null;
    return {
      id: `calibration-checkpoint-${slug}`,
      label: `${calibrationSport(entry) || "Published"} | ${entityName(entry)}`,
      group: calibrationSport(entry) || "Published checkpoints",
      values: { model_ece: model, market_ece: market, ece_gap_model_minus_market: model === null || market === null ? null : Number((model - market).toFixed(6)), n: finite(values.n) ? values.n : null },
      note: typeof entry.floors === "string" ? entry.floors : undefined,
      href: `/analytics/players/calibration/${slug}`,
      sourcePaths: ["model_ece", "market_ece", "n"].map((key) => `entries[${index}].key_numbers.${key}`),
    };
  });
  return {
    id: "calibration-by-game-checkpoint",
    title: "Calibration by game checkpoint",
    sport: "all",
    category: "Calibration diagnostics",
    source: "atlas_calibration_manifest",
    question: "How do published calibration errors vary by sport and game checkpoint?",
    method: "Restates each published time-checkpoint card and subtracts market ECE from model ECE when both values are published. Probability-band cards from the same manifest publish no ECE and are analysed separately.",
    description: "Published model and market calibration errors by sport and game checkpoint.",
    scope: `${rows.length} published sport-by-checkpoint rows; probability-band cards are excluded because they publish no calibration error.`,
    caveat: calibrationFloors(cards) || "The published manifest does not state a shared floor for these checkpoints.",
    status: "Descriptive calibration subset",
    fields: [f("model_ece", "Model ECE", "number", 4), f("market_ece", "Market ECE", "number", 4), f("ece_gap_model_minus_market", "ECE gap: model minus market", "number", 4), f("n", "Published rows", "number", 0)],
    rows,
    formula: "ECE gap (model minus market) = published model_ece - published market_ece.",
    interpretation: "Read each calibration error with its published row count and checkpoint floor; the signed gap only compares the two published ECE values in that row, and checkpoints from different sports are separate populations.",
    references: CALIBRATION_REFERENCES,
    novelty: "Derived analysis",
    asOf: calibrationDate(cards),
  };
}

export function getCalibrationCheckpointResearch(): ResearchAnalysis[] {
  return [buildCalibrationCheckpointResearch(snapshot<CalibrationManifest>("atlas_calibration_manifest"))];
}
