import { field as f, snapshot } from "./labHelpers";
import type { ResearchAnalysis, ResearchReference, ResearchRow } from "./researchTypes";
import { buildBrierPhaseCoverage } from "./brierPhaseCoverage";

type Grain = { n?: unknown; brier_model?: unknown; brier_market?: unknown; brier_clim?: unknown; bss_model_vs_clim?: unknown; bss_market_vs_clim?: unknown; bss_model_vs_market?: unknown; below_floor?: unknown };
type SportScores = { grains?: unknown };
export type BrierSkillScoresSource = { generated_at?: unknown; sports?: unknown };

const REFERENCES: ResearchReference[] = [{
  title: "Published Brier skill-score method",
  url: "https://github.com/neeljshah/court-vision/blob/master/scripts/platformkit/analytics_showcase/brier_skill_scores.py",
}];
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const sportLabel = (sport: string) => sport === "soccer_intl" ? "International soccer" : sport.toUpperCase();
const generatedDate = (value: unknown): string | undefined => typeof value === "string" && Number.isFinite(Date.parse(value)) ? new Date(Date.parse(value)).toISOString().slice(0, 10) : undefined;

function rows(source: BrierSkillScoresSource): ResearchRow[] {
  if (!source.sports || typeof source.sports !== "object" || Array.isArray(source.sports)) return [];
  return Object.entries(source.sports as Record<string, unknown>).flatMap(([sport, entry]) => {
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) return [];
    const scores = entry as SportScores;
    if (!scores.grains || typeof scores.grains !== "object" || Array.isArray(scores.grains)) return [];
    return Object.entries(scores.grains as Record<string, unknown>).flatMap(([grain, value]) => {
      if (!value || typeof value !== "object" || Array.isArray(value)) return [];
      const row = value as Grain;
      if (!finite(row.n) || row.n < 0 || !finite(row.brier_model) || row.brier_model < 0 || !finite(row.brier_market) || row.brier_market < 0 || !finite(row.brier_clim) || row.brier_clim < 0 || !finite(row.bss_model_vs_clim) || !finite(row.bss_market_vs_clim) || !finite(row.bss_model_vs_market)) return [];
      return [{
        id: `brier-skill-${sport}-${grain.replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "")}`,
        label: `${sportLabel(sport)} | ${grain}`,
        group: sportLabel(sport),
        values: { model_brier: row.brier_model, market_brier: row.brier_market, climatology_brier: row.brier_clim, model_vs_climatology_bss: row.bss_model_vs_clim, market_vs_climatology_bss: row.bss_market_vs_clim, model_vs_market_bss: row.bss_model_vs_market, scored_rows: row.n },
        note: `${row.below_floor === true ? "Source flags this row below its support floor. " : "Source support clears its published floor. "}${row.n} scored rows.`,
        sourcePaths: [`sports.${sport}.grains.${grain}.brier_model`, `sports.${sport}.grains.${grain}.brier_market`, `sports.${sport}.grains.${grain}.brier_clim`, `sports.${sport}.grains.${grain}.bss_model_vs_clim`, `sports.${sport}.grains.${grain}.bss_market_vs_clim`, `sports.${sport}.grains.${grain}.bss_model_vs_market`, `sports.${sport}.grains.${grain}.n`, `sports.${sport}.grains.${grain}.below_floor`],
      }];
    });
  }).sort((left, right) => left.group.localeCompare(right.group) || left.label.localeCompare(right.label, undefined, { numeric: true }));
}

export function buildBrierSkillScoresResearch(source: BrierSkillScoresSource): ResearchAnalysis[] {
  const analysisRows = rows(source || {});
  return [{
    id: "brier-skill-score-by-game-phase",
    title: "Brier skill score by sport and game phase",
    sport: "all",
    category: "Calibration diagnostics",
    source: "brier_skill_scores",
    question: "How do published Brier skill scores differ by sport and game phase under named references?",
    method: "Restate each published sport-phase row with its three Brier operands and three Brier skill scores.",
    description: "Published sport-phase rows retain Brier scores and Brier skill scores against climatology and market references.",
    scope: `${analysisRows.length} published sport-phase rows. Source artifact generated ${generatedDate(source?.generated_at) || "on an unpublished date"}.`,
    caveat: "Brier skill scores inherit the source's climatology and market references. Repeated in-game rows share outcomes, and a positive or negative score describes this published corpus rather than a future result.",
    status: "Descriptive calibration subset",
    fields: [f("model_vs_market_bss", "Model versus Market Brier skill score", "number", 4), f("model_vs_climatology_bss", "Model versus Climatology Brier skill score", "number", 4), f("market_vs_climatology_bss", "Market versus Climatology Brier skill score", "number", 4), f("model_brier", "Model Brier", "number", 4), f("market_brier", "Market Brier", "number", 4), f("climatology_brier", "Climatology Brier", "number", 4), f("scored_rows", "Scored rows", "number", 0)],
    rows: analysisRows,
    phaseCoverage: buildBrierPhaseCoverage(source || {}),
    formula: "bss_model_vs_clim = 1 - brier_model / brier_clim. bss_market_vs_clim = 1 - brier_market / brier_clim. bss_model_vs_market = 1 - brier_model / brier_market; n is the published support.",
    bindings: [
      { operand: "brier_model", sourcePath: "sports.*.grains.*.brier_model", valueKey: "model_brier", label: "Model Brier" },
      { operand: "brier_market", sourcePath: "sports.*.grains.*.brier_market", valueKey: "market_brier", label: "Market Brier" },
      { operand: "brier_clim", sourcePath: "sports.*.grains.*.brier_clim", valueKey: "climatology_brier", label: "Climatology Brier" },
      { operand: "bss_model_vs_clim", sourcePath: "sports.*.grains.*.bss_model_vs_clim", valueKey: "model_vs_climatology_bss", label: "Model versus Climatology Brier skill score" },
      { operand: "bss_market_vs_clim", sourcePath: "sports.*.grains.*.bss_market_vs_clim", valueKey: "market_vs_climatology_bss", label: "Market versus Climatology Brier skill score" },
      { operand: "bss_model_vs_market", sourcePath: "sports.*.grains.*.bss_model_vs_market", valueKey: "model_vs_market_bss", label: "Model versus Market Brier skill score" },
      { operand: "n", sourcePath: "sports.*.grains.*.n", valueKey: "scored_rows", label: "Scored rows" },
    ],
    interpretation: "Compare each Brier skill score only with its named reference and read the three Brier operands with the scored-row count.",
    references: REFERENCES,
    novelty: "Derived analysis",
    asOf: generatedDate(source?.generated_at),
  }];
}

export function getBrierSkillScoresResearch(): ResearchAnalysis[] {
  return buildBrierSkillScoresResearch(snapshot<BrierSkillScoresSource>("brier_skill_scores"));
}
