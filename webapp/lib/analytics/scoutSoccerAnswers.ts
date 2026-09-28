import type { AskEntry } from "./askSearch";
import { buildSoccerScoringResearch, type SoccerScoringAtlas } from "./researchSoccerScoring";

const SOURCE = "webapp/public/data/showcase/atlas_soccer_manifest.json";
const METRIC = "clean_sheet_rate_l10";
const WINDOW = "exactly 10 strictly prior all-venue matches; latest per-team match dropped";

export function buildSoccerCleanSheetAnswers(atlas: SoccerScoringAtlas): AskEntry[] {
  const analysis = buildSoccerScoringResearch(atlas);
  return analysis.rows.flatMap<AskEntry>(row => {
    const rate = row.values[METRIC];
    if (typeof rate !== "number" || !Number.isFinite(rate) || rate < 0 || rate > 1 || row.windows?.[METRIC] !== WINDOW) return [];
    const team = row.label;
    const timestamp = row.bindingValues?.source_claim_timestamp;
    const asOf = typeof timestamp === "string" ? timestamp : "unknown";
    const params = new URLSearchParams({ q: team, metric: METRIC, row: row.id });
    return [{
      q: `How often does ${team} keep clean sheets?`,
      alt_phrasings: [
        `${team} clean sheets`,
        `${team} clean-sheet rate`,
        `What is ${team}'s clean-sheet rate?`,
        `What is the clean-sheet rate for ${team}?`,
      ],
      tags: ["soccer", "team", "clean-sheet rate", team],
      bucket: "public-soccer-clean-sheets",
      exactOnly: true,
      a: {
        status: "ok",
        answer: `${team}'s published clean-sheet rate is ${(rate * 100).toFixed(1)}%. A clean sheet means zero goals conceded in a match. This rate is the share of exactly 10 strictly prior all-venue (home or away) matches after the team's latest match was dropped. Source claim timestamp: ${asOf}. Per-team match dates are unpublished. This is a historical descriptive snapshot, not a current result or forecast.`,
        source_artifact: SOURCE,
        source_module_ids: ["atlas_soccer_manifest"],
        as_of: asOf,
        explore_path: `/analytics/research/${analysis.id}/?${params.toString()}`,
      },
    }];
  });
}
