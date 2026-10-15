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

function leadContext(value: string): { label: string; homeLeads: boolean | null } {
  if (value === "lead_00") return { label: "Tied score", homeLeads: null };
  const match = /^lead_([+-])(\d+)_(\d+)$/.exec(value);
  if (!match || Number(match[2]) <= 0 || Number(match[3]) < Number(match[2])) return { label: value, homeLeads: null };
  const homeLeads = match[1] === "+";
  return { label: `Home ${homeLeads ? "leads" : "trails"} ${Number(match[2])}-${Number(match[3])}`, homeLeads };
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
    const context = leadContext(lead);
    const awayWinShare = Number((1 - cell.outcome_rate).toFixed(6));
    const comebackShare = context.homeLeads === null ? null : context.homeLeads ? awayWinShare : cell.outcome_rate;
    const leadingShare = context.homeLeads === null ? null : context.homeLeads ? cell.outcome_rate : awayWinShare;
    const perspective = context.homeLeads === null
      ? "This cell has no defined trailing side; comeback and leading-side shares are unavailable."
      : context.homeLeads ? "Away is trailing; comeback share is 1 - the published home-win rate."
        : "Home is trailing; comeback share is the published home-win rate.";
    return [{
      id: `comeback-${lead}-${time}`,
      label: `${context.label} | ${timeLabel(time)}`,
      group: context.label,
      values: { comeback_share: comebackShare, games: cell.n_games, ticks: cell.n_ticks, leading_side_outcome_share: leadingShare },
      bindingValues: { lead_band: context.label, time_band: timeLabel(time), outcome_rate: cell.outcome_rate, masked_n_lt_30: String(masked) },
      note: `${masked ? "Small-support source cell: n_games < 30; retained and flagged by the published mask. " : "Source cell clears the published n_games mask. "}${perspective}`,
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
    description: "Published home-lead and home-deficit cells show the trailing side's observed win share, alongside game and tick support. Tied cells retain support without a comeback share.",
    scope: `${analysisRows.length} published NBA home-margin/time cells, including tied states and small-support cells that the source flags. The source does not publish an as-of timestamp.`,
    caveat: `${maskRule} Source aggregates are tick-weighted rather than game-weighted, so a game with more recorded ticks has more influence. Comeback share uses the home-win rate when home trails and its complement when home leads. Tied states have no trailing side. These are historical measurements, not a live game or forecast.`,
    status: "Descriptive game-state subset",
    fields: [f("comeback_share", "Observed comeback share", "percent", 2), f("games", "Games", "number", 0), f("ticks", "Recorded ticks", "number", 0), f("leading_side_outcome_share", "Leading-side outcome share", "percent", 2)],
    rows: analysisRows,
    formula: "outcome_rate is the published home-win fraction. Comeback share = 1 - outcome_rate when home leads, or outcome_rate when home trails; tied or unrecognized lead bands have no comeback or leading-side share. lead_band and time_band identify the published source cell; n_games and n_ticks report its support.",
    bindings: [
      { operand: "lead_band", sourcePath: "cells[].lead_band", valueKey: "lead_band", label: "Home margin band" },
      { operand: "time_band", sourcePath: "cells[].time_band", valueKey: "time_band", label: "Time band" },
      { operand: "outcome_rate", sourcePath: "cells[].outcome_rate", valueKey: "outcome_rate", label: "Published home-win rate (fraction)" },
      { operand: "n_games", sourcePath: "cells[].n_games", valueKey: "games", label: "Games" },
      { operand: "n_ticks", sourcePath: "cells[].n_ticks", valueKey: "ticks", label: "Recorded ticks" },
      { operand: "masked_n_lt_30", sourcePath: "cells[].masked_n_lt_30", valueKey: "masked_n_lt_30", label: "Small-support mask" },
    ],
    interpretation: "Higher values mean the trailing side more often won in that published deficit-time cell. Compare support counts and flagged cells before comparing buckets.",
    references: REFERENCES,
    novelty: "Derived analysis",
  }];
}

export function getComebackAtlasResearch(): ResearchAnalysis[] {
  return buildComebackAtlasResearch(snapshot<ComebackAtlasSource>("comeback_atlas"));
}
