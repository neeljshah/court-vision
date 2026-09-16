import { field as f, snapshot } from "./labHelpers";
import type { ResearchAnalysis, ResearchReference, ResearchRow } from "./researchTypes";

type ComebackCell = { lead_band?: unknown; time_band?: unknown; n_games?: unknown; n_ticks?: unknown; outcome_rate?: unknown; masked_n_lt_30?: unknown };
export type ComebackAtlasSource = { cells?: unknown; mask_rule?: unknown };

const REFERENCES: ResearchReference[] = [{
  title: "Published NBA reliability-map method",
  url: "https://github.com/neeljshah/court-vision/blob/master/scripts/platformkit/analytics_showcase/comeback_atlas.py",
}];
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const probability = (value: unknown): value is number => finite(value) && value >= 0 && value <= 1;

function deficitLabel(value: string): string {
  const match = /^lead_\+(\d+)_(\d+)$/.exec(value);
  return match ? `Deficit ${Number(match[1])}-${Number(match[2])}` : value;
}
function timeLabel(value: string): string {
  const match = /^rem_(\d+)_(\d+)$/.exec(value);
  return match ? `${Number(match[1])}-${Number(match[2])} remaining` : value === "ot" ? "Overtime" : value;
}
function rows(source: ComebackAtlasSource): ResearchRow[] {
  if (!Array.isArray(source.cells)) return [];
  return (source.cells as ComebackCell[]).flatMap((cell) => {
    const lead = typeof cell.lead_band === "string" ? cell.lead_band : "";
    const time = typeof cell.time_band === "string" ? cell.time_band : "";
    if (!lead || !time || !finite(cell.n_games) || cell.n_games < 0 || !finite(cell.n_ticks) || cell.n_ticks < 0 || !probability(cell.outcome_rate)) return [];
    const masked = cell.masked_n_lt_30 === true;
    return [{
      id: `comeback-${lead}-${time}`,
      label: `${deficitLabel(lead)} | ${timeLabel(time)}`,
      group: deficitLabel(lead),
      values: { comeback_share: Number((1 - cell.outcome_rate).toFixed(6)), games: cell.n_games, ticks: cell.n_ticks, leading_side_outcome_share: cell.outcome_rate },
      note: `${masked ? "Small-support source cell: n_games < 30; retained and flagged by the published mask. " : "Source cell clears the published n_games mask. "}Comeback share is derived as 1 - the published leading-side outcome rate.`,
      sourcePaths: ["cells[].lead_band", "cells[].time_band", "cells[].outcome_rate", "cells[].n_games", "cells[].n_ticks", "cells[].masked_n_lt_30"],
    }];
  }).sort((left, right) => left.group.localeCompare(right.group, undefined, { numeric: true }) || left.label.localeCompare(right.label, undefined, { numeric: true }));
}

export function buildComebackAtlasResearch(source: ComebackAtlasSource): ResearchAnalysis[] {
  const analysisRows = rows(source || {});
  const maskRule = typeof source?.mask_rule === "string" ? source.mask_rule : "The source mask rule is unavailable.";
  return [{
    id: "comeback-rates-deficit-time",
    title: "Comeback rates by deficit and time remaining",
    sport: "nba",
    category: "Game-state context",
    source: "comeback_atlas",
    description: "Each published deficit-by-clock cell is restated as the trailing side's observed comeback share, alongside game and tick support.",
    scope: `${analysisRows.length} published NBA deficit-time cells, including small-support cells that the source flags. The source does not publish an as-of timestamp.`,
    caveat: `${maskRule} Source aggregates are tick-weighted rather than game-weighted, so a game with more recorded ticks has more influence. The displayed comeback share is derived from the leading-side outcome rate and does not describe a live game or forecast.`,
    status: "Descriptive game-state subset",
    fields: [f("comeback_share", "Observed comeback share", "percent", 2), f("games", "Games", "number", 0), f("ticks", "Recorded ticks", "number", 0), f("leading_side_outcome_share", "Leading-side outcome share", "percent", 2)],
    rows: analysisRows,
    formula: "Displayed comeback share = 1 - published outcome_rate, where outcome_rate is the source cell's leading-side outcome share.",
    interpretation: "Higher values mean the trailing side more often won in that published deficit-time cell. Compare support counts and flagged cells before comparing buckets.",
    references: REFERENCES,
    novelty: "Derived analysis",
  }];
}

export function getComebackAtlasResearch(): ResearchAnalysis[] {
  return buildComebackAtlasResearch(snapshot<ComebackAtlasSource>("comeback_atlas"));
}
