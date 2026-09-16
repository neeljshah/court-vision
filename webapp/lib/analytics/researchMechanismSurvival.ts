import { field as f, snapshot } from "./labHelpers";
import type { ResearchAnalysis, ResearchReference, ResearchRow } from "./researchTypes";

type Summary = { n?: unknown; n_testable?: unknown; n_confirmed?: unknown; n_not_testable?: unknown; survival_rate?: unknown; not_testable_share?: unknown };
export type MechanismSurvivalSource = { by_sport?: unknown; by_category?: unknown };

const REFERENCES: ResearchReference[] = [{
  title: "Published mechanism-survival method",
  url: "https://github.com/neeljshah/court-vision/blob/master/scripts/platformkit/analytics_showcase/mechanism_survival.py",
}];
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const label = (value: string) => value.replaceAll("_", " ").replace(/\b\w/g, letter => letter.toUpperCase());

function summaryRows(source: Record<string, unknown>, prefix: "by_sport" | "by_category", group: string): ResearchRow[] {
  return Object.entries(source).flatMap(([name, value]) => {
    const row = value as Summary;
    if (!finite(row.n) || row.n < 0 || !finite(row.n_testable) || row.n_testable < 0 || !finite(row.n_confirmed) || row.n_confirmed < 0 || !finite(row.n_not_testable) || row.n_not_testable < 0 || !finite(row.survival_rate) || row.survival_rate < 0 || row.survival_rate > 1 || !finite(row.not_testable_share) || row.not_testable_share < 0 || row.not_testable_share > 1) return [];
    return [{
      id: `mechanism-survival-${prefix}-${name}`,
      label: label(name),
      group,
      values: { hypotheses: row.n, testable_hypotheses: row.n_testable, confirmed_hypotheses: row.n_confirmed, not_testable_hypotheses: row.n_not_testable, survival_share: row.survival_rate, not_testable_share: row.not_testable_share },
      note: `${row.n_testable} testable hypotheses; ${row.n_confirmed} carry a confirmed source verdict.`,
      sourcePaths: [`${prefix}.${name}.n`, `${prefix}.${name}.n_testable`, `${prefix}.${name}.n_confirmed`, `${prefix}.${name}.n_not_testable`, `${prefix}.${name}.survival_rate`, `${prefix}.${name}.not_testable_share`],
    }];
  });
}

function rows(source: MechanismSurvivalSource): ResearchRow[] {
  const categories = source.by_category && typeof source.by_category === "object" && !Array.isArray(source.by_category) ? summaryRows(source.by_category as Record<string, unknown>, "by_category", "Mechanism family") : [];
  const sports = source.by_sport && typeof source.by_sport === "object" && !Array.isArray(source.by_sport) ? summaryRows(source.by_sport as Record<string, unknown>, "by_sport", "Sport") : [];
  return [...categories, ...sports].sort((left, right) => left.group.localeCompare(right.group) || left.label.localeCompare(right.label));
}

export function buildMechanismSurvivalResearch(source: MechanismSurvivalSource): ResearchAnalysis[] {
  const analysisRows = rows(source || {});
  return [{
    id: "hypothesis-survival-by-mechanism",
    title: "Published hypothesis survival by mechanism family",
    sport: "all",
    category: "Validation coverage",
    source: "mechanism_survival",
    question: "How many published hypotheses were tested, confirmed, or left untestable by mechanism family and sport?",
    method: "Restate the source's latest-verdict summaries for every published mechanism family and sport.",
    description: "Published survival summaries retain total, testable, confirmed, and untestable hypothesis counts with their two shares.",
    scope: `${analysisRows.length} published mechanism-family and sport summaries. The source does not publish an as-of timestamp.`,
    caveat: "The summaries use each hypothesis's latest recorded verdict. A confirmation count is not a causal estimate, and differing corpus coverage can change the mix of testable hypotheses across groups.",
    status: "Descriptive validation subset",
    fields: [f("survival_share", "Survival share", "percent", 2), f("confirmed_hypotheses", "Confirmed hypotheses", "number", 0), f("testable_hypotheses", "Testable hypotheses", "number", 0), f("not_testable_share", "Not testable share", "percent", 2), f("not_testable_hypotheses", "Not testable hypotheses", "number", 0), f("hypotheses", "Hypotheses", "number", 0)],
    rows: analysisRows,
    formula: "Survival share = Confirmed hypotheses / Testable hypotheses. Not testable share = Not testable hypotheses / Hypotheses.",
    interpretation: "Compare survival share only with testable-hypothesis support and retain the untestable share when comparing mechanism families or sports.",
    references: REFERENCES,
    novelty: "Derived analysis",
  }];
}

export function getMechanismSurvivalResearch(): ResearchAnalysis[] {
  return buildMechanismSurvivalResearch(snapshot<MechanismSurvivalSource>("mechanism_survival"));
}
