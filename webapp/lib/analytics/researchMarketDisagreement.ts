import { field as f, snapshot } from "./labHelpers";
import type { ResearchAnalysis, ResearchReference, ResearchRow } from "./researchTypes";

type Bucket = { bucket?: unknown; n?: unknown; model_brier?: unknown; market_brier?: unknown; model_closer_rate?: unknown };
export type MarketDisagreementSource = { sports?: unknown };

const REFERENCES: ResearchReference[] = [{
  title: "Published market-disagreement method",
  url: "https://github.com/neeljshah/court-vision/blob/master/scripts/platformkit/analytics_showcase/market_disagreement_profile.py",
}];
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const probability = (value: unknown): value is number => finite(value) && value >= 0 && value <= 1;
const sportLabel = (sport: string) => sport === "soccer_intl" ? "International soccer" : sport.toUpperCase();

function rows(source: MarketDisagreementSource): ResearchRow[] {
  if (!source.sports || typeof source.sports !== "object" || Array.isArray(source.sports)) return [];
  return Object.entries(source.sports as Record<string, unknown>).flatMap(([sport, entries]) => {
    if (!Array.isArray(entries)) return [];
    return entries.flatMap((entry) => {
      const row = entry as Bucket;
      const bucket = typeof row.bucket === "string" ? row.bucket.trim() : "";
      if (!bucket || !finite(row.n) || row.n < 0 || !finite(row.model_brier) || row.model_brier < 0 || !finite(row.market_brier) || row.market_brier < 0 || !probability(row.model_closer_rate)) return [];
      return [{
        id: `market-disagreement-${sport}-${bucket.replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "")}`,
        label: `${sportLabel(sport)} | ${bucket}`,
        group: sportLabel(sport),
        values: { model_brier: row.model_brier, market_brier: row.market_brier, model_closer_rate: row.model_closer_rate, scored_rows: row.n },
        note: `Published disagreement bucket with ${row.n} scored rows.`,
        sourcePaths: [`sports.${sport}[].bucket`, `sports.${sport}[].model_brier`, `sports.${sport}[].market_brier`, `sports.${sport}[].model_closer_rate`, `sports.${sport}[].n`],
      }];
    });
  }).sort((left, right) => left.group.localeCompare(right.group) || left.label.localeCompare(right.label, undefined, { numeric: true }));
}

export function buildMarketDisagreementResearch(source: MarketDisagreementSource): ResearchAnalysis[] {
  const analysisRows = rows(source || {});
  return [{
    id: "market-disagreement-brier-by-bucket",
    title: "Model and market Brier by disagreement bucket",
    sport: "all",
    category: "Calibration diagnostics",
    source: "market_disagreement_profile",
    question: "How do model and market Brier scores vary when their published probabilities are farther apart?",
    method: "Bucket rows by the published absolute model-probability-minus-market-probability range, preserving the two Brier scores, model-closer rate, and support.",
    description: "Published rows group model-market probability gaps and retain each side's Brier score, model-closer rate, and scored-row support.",
    scope: `${analysisRows.length} published sport-by-disagreement buckets. The source does not publish an as-of timestamp.`,
    caveat: "Buckets describe the published joined corpora rather than independent games. The model-closer rate records the source's row-level comparison and is not a forecast or causal estimate.",
    status: "Descriptive calibration subset",
    fields: [f("model_brier", "Model Brier", "number", 4), f("market_brier", "Market Brier", "number", 4), f("model_closer_rate", "Model closer rate", "percent", 2), f("scored_rows", "Scored rows", "number", 0)],
    rows: analysisRows,
    formula: "model_brier, market_brier, model_closer_rate, and n are copied from the published absolute model-probability-minus-market-probability bucket.",
    bindings: [
      { operand: "model_brier", sourcePath: "sports.*[].model_brier", valueKey: "model_brier", label: "Model Brier" },
      { operand: "market_brier", sourcePath: "sports.*[].market_brier", valueKey: "market_brier", label: "Market Brier" },
      { operand: "model_closer_rate", sourcePath: "sports.*[].model_closer_rate", valueKey: "model_closer_rate", label: "Model closer rate" },
      { operand: "n", sourcePath: "sports.*[].n", valueKey: "scored_rows", label: "Scored rows" },
    ],
    interpretation: "Compare Model Brier and Market Brier within the same sport and disagreement bucket, with the scored-row count alongside both measurements.",
    references: REFERENCES,
    novelty: "Derived analysis",
  }];
}

export function getMarketDisagreementResearch(): ResearchAnalysis[] {
  return buildMarketDisagreementResearch(snapshot<MarketDisagreementSource>("market_disagreement_profile"));
}
