import { field as f, snapshot } from "./labHelpers";
import type { ResearchAnalysis, ResearchReference, ResearchRow } from "./researchTypes";

type PaceCell = { pace?: unknown; fav_win_prob?: unknown; upset_prob?: unknown };
type PaceCurve = { fav_strength_at_ref_pace?: unknown; by_pace?: unknown };
export type PaceVarianceSource = { as_of?: unknown; curves?: unknown };

const REFERENCES: ResearchReference[] = [{
  title: "Published pace-variance formulation",
  url: "https://github.com/neeljshah/court-vision/blob/master/scripts/platformkit/analytics_showcase/cf_pace_variance.py",
}];

const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const probability = (value: unknown): value is number => finite(value) && value >= 0 && value <= 1;
const asDate = (value: unknown): string | undefined => typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(`${value}T00:00:00Z`)) ? value : undefined;

function rows(source: PaceVarianceSource): ResearchRow[] {
  if (!Array.isArray(source.curves)) return [];
  const output: Array<ResearchRow & { strength: number; pace: number }> = [];
  for (const curve of source.curves as PaceCurve[]) {
    if (!probability(curve.fav_strength_at_ref_pace) || !Array.isArray(curve.by_pace)) continue;
    for (const cell of curve.by_pace as PaceCell[]) {
      if (!finite(cell.pace) || cell.pace <= 0 || !probability(cell.fav_win_prob) || !probability(cell.upset_prob)) continue;
      output.push({
        id: `pace-${curve.fav_strength_at_ref_pace}-${cell.pace}`,
        label: `${Math.round(curve.fav_strength_at_ref_pace * 100)}% favorite at reference pace | ${cell.pace} pace`,
        group: `${Math.round(curve.fav_strength_at_ref_pace * 100)}% reference favorite`,
        values: { pace: cell.pace, favorite_win_probability: cell.fav_win_prob, trailing_win_probability: cell.upset_prob, reference_favorite_probability: curve.fav_strength_at_ref_pace },
        note: "Published simulation cell. No game count is supplied for this parameter grid.",
        sourcePaths: ["curves[].fav_strength_at_ref_pace", "curves[].by_pace[].pace", "curves[].by_pace[].fav_win_prob", "curves[].by_pace[].upset_prob"],
        strength: curve.fav_strength_at_ref_pace,
        pace: cell.pace,
      });
    }
  }
  return output.sort((left, right) => left.strength - right.strength || left.pace - right.pace || left.id.localeCompare(right.id)).map(({ strength: _strength, pace: _pace, ...row }) => row);
}

export function buildPaceVarianceResearch(source: PaceVarianceSource): ResearchAnalysis[] {
  const analysisRows = rows(source || {});
  return [{
    id: "pace-variance-favorite-probability",
    title: "Favorite win probability across pace assumptions",
    sport: "nba",
    category: "Counterfactual context",
    source: "cf_pace_variance",
    description: "Published simulation cells compare favorite and trailing-side win probabilities across pace assumptions and three reference strengths.",
    scope: `${analysisRows.length} published pace-strength cells. The source supplies a parameter grid rather than an observed-game sample.`,
    caveat: "This is a declared counterfactual simulation, not an observed game table. Its outputs depend on the published pace and strength assumptions, and do not isolate team quality, roster availability, or schedule context. It describes the supplied formulation and is not a game forecast.",
    status: "Descriptive simulation",
    fields: [f("pace", "Pace assumption", "number", 1), f("favorite_win_probability", "Favorite win probability", "percent", 2), f("trailing_win_probability", "Trailing-side win probability", "percent", 2), f("reference_favorite_probability", "Reference favorite probability", "percent", 2)],
    rows: analysisRows,
    formula: "Each displayed value is copied from the published curve cell at a stated reference favorite probability and pace assumption.",
    interpretation: "Compare rows within a reference-strength group to see how the published formulation changes as the pace input changes.",
    references: REFERENCES,
    novelty: "Derived analysis",
    asOf: asDate(source?.as_of),
  }];
}

export function getPaceVarianceResearch(): ResearchAnalysis[] {
  return buildPaceVarianceResearch(snapshot<PaceVarianceSource>("cf_pace_variance"));
}
