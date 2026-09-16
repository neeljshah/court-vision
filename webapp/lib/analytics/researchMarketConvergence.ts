import { field as f, snapshot } from "./labHelpers";
import type { ResearchAnalysis, ResearchReference, ResearchRow } from "./researchTypes";

type Checkpoint = { n?: unknown; mean_gap?: unknown; median_gap?: unknown; mean_entropy_market_bits?: unknown; mean_entropy_model_bits?: unknown; mean_market_prob?: unknown; mean_model_prob?: unknown };
export type MarketConvergenceSource = { checkpoints?: unknown; min_n?: unknown };

const REFERENCES: ResearchReference[] = [{
  title: "Published market-convergence method",
  url: "https://github.com/neeljshah/court-vision/blob/master/scripts/platformkit/analytics_showcase/market_convergence.py",
}];
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const probability = (value: unknown): value is number => finite(value) && value >= 0 && value <= 1;
const sportLabel = (sport: string) => sport === "soccer_intl" ? "International soccer" : sport.toUpperCase();
const checkpointLabel = (sport: string, checkpoint: string) => sport === "mlb" ? `Inning ${checkpoint}` : `${checkpoint}'`;

function rows(source: MarketConvergenceSource): ResearchRow[] {
  if (!source.checkpoints || typeof source.checkpoints !== "object" || Array.isArray(source.checkpoints)) return [];
  return Object.entries(source.checkpoints as Record<string, unknown>).flatMap(([sport, checkpoints]) => {
    if (!checkpoints || typeof checkpoints !== "object" || Array.isArray(checkpoints)) return [];
    return Object.entries(checkpoints as Record<string, unknown>).flatMap(([checkpoint, entry]) => {
      const row = entry as Checkpoint;
      if (!finite(row.n) || row.n < 0 || !finite(row.mean_gap) || row.mean_gap < 0 || !finite(row.median_gap) || row.median_gap < 0 || !finite(row.mean_entropy_market_bits) || row.mean_entropy_market_bits < 0 || !finite(row.mean_entropy_model_bits) || row.mean_entropy_model_bits < 0 || !probability(row.mean_market_prob) || !probability(row.mean_model_prob)) return [];
      return [{
        id: `market-convergence-${sport}-${checkpoint}`,
        label: `${sportLabel(sport)} | ${checkpointLabel(sport, checkpoint)}`,
        group: sportLabel(sport),
        values: { mean_gap: row.mean_gap, median_gap: row.median_gap, market_entropy_bits: row.mean_entropy_market_bits, model_entropy_bits: row.mean_entropy_model_bits, mean_market_probability: row.mean_market_prob, mean_model_probability: row.mean_model_prob, scored_rows: row.n },
        note: `Published checkpoint support: ${row.n} rows.`,
        sourcePaths: [`checkpoints.${sport}.${checkpoint}.mean_gap`, `checkpoints.${sport}.${checkpoint}.median_gap`, `checkpoints.${sport}.${checkpoint}.mean_entropy_market_bits`, `checkpoints.${sport}.${checkpoint}.mean_entropy_model_bits`, `checkpoints.${sport}.${checkpoint}.mean_market_prob`, `checkpoints.${sport}.${checkpoint}.mean_model_prob`, `checkpoints.${sport}.${checkpoint}.n`],
      }];
    });
  }).sort((left, right) => left.group.localeCompare(right.group) || left.label.localeCompare(right.label, undefined, { numeric: true }));
}

export function buildMarketConvergenceResearch(source: MarketConvergenceSource): ResearchAnalysis[] {
  const analysisRows = rows(source || {});
  const minimum = finite(source?.min_n) && source.min_n >= 0 ? source.min_n : null;
  return [{
    id: "market-convergence-by-checkpoint",
    title: "Model-market convergence by game checkpoint",
    sport: "all",
    category: "In-game calibration",
    source: "market_convergence",
    question: "How do published model-market probability gaps and uncertainty change across game checkpoints?",
    method: "Restate every published sport-checkpoint row with absolute probability gaps, entropy measurements, mean probabilities, and support.",
    description: "Published checkpoints retain model-market probability gaps, uncertainty in bits, mean probabilities, and scored-row support.",
    scope: `${analysisRows.length} published MLB-inning and international-soccer-minute checkpoints${minimum === null ? "." : ` with a source minimum of ${minimum} rows.`}`,
    caveat: "The source describes agreement and uncertainty at repeated in-game checkpoints, not independent forecasts. Entropy declines as outcomes resolve and does not by itself establish model quality.",
    status: "Descriptive checkpoint subset",
    fields: [f("mean_gap", "Mean absolute probability gap", "percent", 2), f("median_gap", "Median absolute probability gap", "percent", 2), f("market_entropy_bits", "Market entropy", "number", 3), f("model_entropy_bits", "Model entropy", "number", 3), f("mean_market_probability", "Mean market probability", "percent", 2), f("mean_model_probability", "Mean model probability", "percent", 2), f("scored_rows", "Scored rows", "number", 0)],
    rows: analysisRows,
    formula: "Mean absolute probability gap, Median absolute probability gap, Market entropy, Model entropy, Mean market probability, Mean model probability, and Scored rows are copied from the same published checkpoint.",
    interpretation: "Read the gap with both entropy measurements at the same checkpoint; later game time can change agreement and uncertainty together.",
    references: REFERENCES,
    novelty: "Derived analysis",
  }];
}

export function getMarketConvergenceResearch(): ResearchAnalysis[] {
  return buildMarketConvergenceResearch(snapshot<MarketConvergenceSource>("market_convergence"));
}
