import { field as f, snapshot } from "./labHelpers";
import type { ResearchAnalysis, ResearchReference, ResearchRow } from "./researchTypes";

type Checkpoint = { n?: unknown; model_brier?: unknown; market_brier?: unknown; naive_brier?: unknown; market_minus_model_brier?: unknown };
export type InformationArrivalSource = { checkpoints?: unknown };

const REFERENCES: ResearchReference[] = [{
  title: "Published information-arrival method",
  url: "https://github.com/neeljshah/court-vision/blob/master/scripts/platformkit/analytics_showcase/info_arrival_curve.py",
}];
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const sportLabel = (sport: string) => sport === "soccer_intl" ? "International soccer" : sport.toUpperCase();
const checkpointLabel = (sport: string, checkpoint: string) => sport === "mlb" ? `Inning ${checkpoint}` : `${checkpoint}'`;

function rows(source: InformationArrivalSource): ResearchRow[] {
  if (!source.checkpoints || typeof source.checkpoints !== "object" || Array.isArray(source.checkpoints)) return [];
  return Object.entries(source.checkpoints as Record<string, unknown>).flatMap(([sport, checkpoints]) => {
    if (!checkpoints || typeof checkpoints !== "object" || Array.isArray(checkpoints)) return [];
    return Object.entries(checkpoints as Record<string, unknown>).flatMap(([checkpoint, entry]) => {
      const row = entry as Checkpoint;
      if (!finite(row.n) || row.n < 0 || !finite(row.model_brier) || row.model_brier < 0 || !finite(row.market_brier) || row.market_brier < 0 || !finite(row.naive_brier) || row.naive_brier < 0 || !finite(row.market_minus_model_brier)) return [];
      const smallSupport = row.n < 30;
      return [{
        id: `information-arrival-${sport}-${checkpoint}`,
        label: `${sportLabel(sport)} | ${checkpointLabel(sport, checkpoint)}`,
        group: sportLabel(sport),
        values: { model_brier: row.model_brier, market_brier: row.market_brier, naive_brier: row.naive_brier, market_minus_model_brier: row.market_minus_model_brier, scored_rows: row.n },
        note: `${smallSupport ? "Small support: " : "Published support: "}${row.n} scored rows${smallSupport ? "; retained for inspection below the 30-row review threshold." : "."}`,
        sourcePaths: [`checkpoints.${sport}.${checkpoint}.model_brier`, `checkpoints.${sport}.${checkpoint}.market_brier`, `checkpoints.${sport}.${checkpoint}.naive_brier`, `checkpoints.${sport}.${checkpoint}.market_minus_model_brier`, `checkpoints.${sport}.${checkpoint}.n`],
      }];
    });
  }).sort((left, right) => left.group.localeCompare(right.group) || left.values.scored_rows! - right.values.scored_rows! || left.label.localeCompare(right.label, undefined, { numeric: true }));
}

export function buildInformationArrivalResearch(source: InformationArrivalSource): ResearchAnalysis[] {
  const analysisRows = rows(source || {});
  return [{
    id: "information-arrival-brier-by-checkpoint",
    title: "Model and market Brier by game checkpoint",
    sport: "all",
    category: "In-game calibration",
    source: "info_arrival_curve",
    question: "How do the published model, market, and naive Brier scores change across game checkpoints?",
    method: "Restate every published sport-checkpoint row with its model, market, naive, and market-minus-model Brier measurements.",
    description: "Published checkpoint rows compare model, market, and naive Brier scores with the market-minus-model Brier difference.",
    scope: `${analysisRows.length} published MLB-inning and international-soccer-minute checkpoints. The source does not publish an as-of timestamp.`,
    caveat: "Checkpoint rows are repeated observations within games, so scored rows are not an independent-game count. Rows with fewer than 30 scored observations remain visible and are flagged for review.",
    status: "Descriptive calibration subset",
    fields: [f("market_minus_model_brier", "Market Brier minus Model Brier", "number", 4), f("model_brier", "Model Brier", "number", 4), f("market_brier", "Market Brier", "number", 4), f("naive_brier", "Naive Brier", "number", 4), f("scored_rows", "Scored rows", "number", 0)],
    rows: analysisRows,
    formula: "Market Brier minus Model Brier = Market Brier - Model Brier. Naive Brier and Scored rows are copied from the same published checkpoint.",
    interpretation: "Compare all Brier measurements at the same sport and game checkpoint before comparing a different phase of play.",
    references: REFERENCES,
    novelty: "Derived analysis",
  }];
}

export function getInformationArrivalResearch(): ResearchAnalysis[] {
  return buildInformationArrivalResearch(snapshot<InformationArrivalSource>("info_arrival_curve"));
}
