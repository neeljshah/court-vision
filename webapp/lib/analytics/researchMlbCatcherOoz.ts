import { field as f, snapshot } from "./labHelpers";
import type { ResearchAnalysis, ResearchReference, ResearchRow } from "./researchTypes";

type Catcher = { name?: unknown; n_ooz_called?: unknown; ooz_strike_rate?: unknown };
export type MlbCatcherOozSource = { catcher_ooz?: { top?: unknown; bottom?: unknown }; observation_window?: { as_of?: unknown } };

const REFERENCES: ResearchReference[] = [{
  title: "Published MLB descriptive-leaderboard method",
  url: "https://github.com/neeljshah/court-vision/blob/master/scripts/platformkit/analytics_showcase/mlb_descriptive_leaderboards.py",
}];
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const asOf = (value: unknown) => typeof value === "string" && Number.isFinite(Date.parse(value)) ? new Date(Date.parse(value)).toISOString().slice(0, 10) : undefined;

function rows(source: MlbCatcherOozSource): ResearchRow[] {
  const lists = [["top", source.catcher_ooz?.top], ["bottom", source.catcher_ooz?.bottom]] as const;
  return lists.flatMap(([selection, catchers]) => {
    if (!Array.isArray(catchers)) return [];
    return (catchers as Catcher[]).flatMap((catcher, index) => {
      if (typeof catcher.name !== "string" || !catcher.name || !finite(catcher.n_ooz_called) || catcher.n_ooz_called < 0 || !finite(catcher.ooz_strike_rate) || catcher.ooz_strike_rate < 0 || catcher.ooz_strike_rate > 1) return [];
      return [{
        id: `catcher-ooz-${selection}-${catcher.name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-${index}`,
        label: catcher.name,
        group: "MLB catchers",
        values: { out_of_zone_strike_rate: catcher.ooz_strike_rate, out_of_zone_called_pitches: catcher.n_ooz_called },
        note: `${selection === "top" ? "Upper" : "Lower"} published selection.`,
        sourcePaths: [`catcher_ooz.${selection}[].name`, `catcher_ooz.${selection}[].ooz_strike_rate`, `catcher_ooz.${selection}[].n_ooz_called`],
      }];
    });
  }).sort((left, right) => right.values.out_of_zone_strike_rate! - left.values.out_of_zone_strike_rate! || left.label.localeCompare(right.label));
}

export function buildMlbCatcherOozResearch(source: MlbCatcherOozSource): ResearchAnalysis[] {
  const analysisRows = rows(source || {});
  return [{
    id: "mlb-catcher-out-of-zone-strike-rate",
    title: "MLB catcher out-of-zone strike rate selections",
    sport: "mlb",
    category: "Descriptive leaderboards",
    source: "mlb_descriptive_leaderboards",
    question: "Which published MLB catchers appear in the upper and lower out-of-zone strike rate selections, and what support is shown for each?",
    method: "Restate the source's published upper and lower catcher selections with out-of-zone strike rate and out-of-zone called-pitch count.",
    description: "Published catcher selections retain their out-of-zone strike rate and called-pitch support from the fixed Statcast corpus slice.",
    scope: `${analysisRows.length} published catcher selections from the source's fixed 2022-2023 corpus slice.`,
    caveat: "The source describes this as a crude out-of-zone called-or-swung-strike measure, not a framing measure. It is a fixed historical slice and does not adjust for pitcher, batter, count, or location mix.",
    status: "Descriptive MLB subset",
    fields: [f("out_of_zone_strike_rate", "Out-of-zone strike rate", "percent", 2), f("out_of_zone_called_pitches", "Out-of-zone called pitches", "number", 0)],
    rows: analysisRows,
    formula: "Out-of-zone strike rate is copied from the published ooz_strike_rate field. Out-of-zone called pitches is copied from the published n_ooz_called field.",
    interpretation: "Read out-of-zone strike rate with out-of-zone called pitches; this selection is descriptive and is not a player-quality ranking.",
    references: REFERENCES,
    novelty: "Derived analysis",
    asOf: asOf(source?.observation_window?.as_of),
  }];
}

export function getMlbCatcherOozResearch(): ResearchAnalysis[] {
  return buildMlbCatcherOozResearch(snapshot<MlbCatcherOozSource>("mlb_descriptive_leaderboards"));
}
