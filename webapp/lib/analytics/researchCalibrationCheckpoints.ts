import { field as f, snapshot } from "./labHelpers";
import { entrySlugs, entityName, type RawEntry } from "./comparisonData";
import type { ResearchAnalysis, ResearchReference, ResearchRow } from "./researchTypes";

export type CalibrationEntry = RawEntry & { sport?: unknown; card_type?: unknown };
export type CalibrationManifest = { entries?: CalibrationEntry[] };

const REFERENCES: ResearchReference[] = [{
  title: "Published calibration checkpoint atlas",
  url: "https://github.com/neeljshah/court-vision/blob/master/webapp/public/data/showcase/atlas_calibration_manifest.json",
}];
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);

function date(entries: RawEntry[]): string | undefined {
  const values = entries.map((entry) => typeof entry.as_of === "string" ? entry.as_of.slice(0, 10) : "");
  return values.length && values.every((value) => /^\d{4}-\d{2}-\d{2}$/.test(value)) && new Set(values).size === 1 ? values[0] : undefined;
}

export function buildCalibrationCheckpointResearch(manifest: CalibrationManifest): ResearchAnalysis {
  const entries = manifest.entries || [];
  const rows: ResearchRow[] = entrySlugs(entries).map(({ slug, entry }, index) => {
    const checkpoint = entry as CalibrationEntry;
    const values = entry.key_numbers || {};
    const model = finite(values.model_ece) ? values.model_ece : null;
    const market = finite(values.market_ece) ? values.market_ece : null;
    return {
      id: `calibration-checkpoint-${slug || index + 1}`,
      label: `${typeof checkpoint.sport === "string" ? checkpoint.sport.toUpperCase() : "Published"} | ${entityName(entry)}`,
      group: typeof checkpoint.sport === "string" ? checkpoint.sport.toUpperCase() : "Published checkpoints",
      values: { model_ece: model, market_ece: market, ece_gap_model_minus_market: model === null || market === null ? null : Number((model - market).toFixed(6)), n: finite(values.n) ? values.n : null },
      note: typeof entry.floors === "string" ? entry.floors : undefined,
      href: `/analytics/players/calibration/${slug}`,
      sourcePaths: ["model_ece", "market_ece", "n"].map((key) => `entries[${index}].key_numbers.${key}`),
    };
  });
  const publishedFloors = [...new Set(entries.map((entry) => entry.floors).filter((value): value is string => typeof value === "string" && value.trim().length > 0))].join(" ");
  return {
    id: "calibration-by-game-checkpoint",
    title: "Calibration by game checkpoint",
    sport: "all",
    category: "Calibration diagnostics",
    source: "atlas_calibration_manifest",
    question: "How do published calibration errors vary by sport and game checkpoint?",
    method: "Restates each published checkpoint card and subtracts market ECE from model ECE when both values are published.",
    description: "Published model and market calibration errors by sport and game checkpoint.",
    scope: `${rows.length} published sport-by-checkpoint rows.`,
    caveat: publishedFloors || "The published manifest does not state a shared floor for these checkpoints.",
    status: "Descriptive calibration subset",
    fields: [f("model_ece", "Model ECE", "number", 4), f("market_ece", "Market ECE", "number", 4), f("ece_gap_model_minus_market", "ECE gap: model minus market", "number", 4), f("n", "Published rows", "number", 0)],
    rows,
    formula: "ECE gap (model minus market) = published model_ece - published market_ece.",
    interpretation: "Read each calibration error with its published row count and checkpoint floor; the signed gap only compares the two published ECE values in that row.",
    references: REFERENCES,
    novelty: "Derived analysis",
    asOf: date(entries),
  };
}

export function getCalibrationCheckpointResearch(): ResearchAnalysis[] {
  return [buildCalibrationCheckpointResearch(snapshot<CalibrationManifest>("atlas_calibration_manifest"))];
}
