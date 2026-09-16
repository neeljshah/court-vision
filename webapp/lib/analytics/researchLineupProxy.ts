import { field as f, snapshot } from "./labHelpers";
import type { ResearchAnalysis, ResearchReference, ResearchRow } from "./researchTypes";

type Player = { team?: unknown; player_name?: unknown; n_active?: unknown; n_missed?: unknown; win_rate_active?: unknown; win_rate_missed?: unknown; delta_win_rate?: unknown; ci95_offset?: unknown };
export type LineupProxySource = { as_of?: unknown; players?: unknown; floors?: { min_active?: unknown; min_missed?: unknown }; confound?: unknown };

const REFERENCES: ResearchReference[] = [{
  title: "Published active-versus-missed method",
  url: "https://github.com/neeljshah/court-vision/blob/master/scripts/platformkit/analytics_showcase/ctx_lineup_proxy.py",
}];
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const probability = (value: unknown): value is number => finite(value) && value >= 0 && value <= 1;

function rows(source: LineupProxySource): ResearchRow[] {
  if (!Array.isArray(source.players)) return [];
  return (source.players as Player[]).flatMap((player) => {
    const team = typeof player.team === "string" ? player.team.trim() : "";
    const name = typeof player.player_name === "string" ? player.player_name.trim() : "";
    const interval = Array.isArray(player.ci95_offset) ? player.ci95_offset : [];
    const halfWidth = interval.length === 2 && finite(interval[0]) && finite(interval[1]) && interval[0] <= 0 && interval[1] >= 0 ? Math.abs(interval[1]) : null;
    if (!team || !name || !finite(player.n_active) || !finite(player.n_missed) || player.n_active < 0 || player.n_missed < 0 || !probability(player.win_rate_active) || !probability(player.win_rate_missed) || !finite(player.delta_win_rate) || halfWidth === null) return [];
    return [{
      id: `lineup-proxy-${team.toLowerCase()}-${name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`,
      label: `${name} (${team})`,
      group: "Player tenure window",
      values: { win_rate_active: player.win_rate_active, win_rate_missed: player.win_rate_missed, win_rate_difference: player.delta_win_rate, wald_95_half_width: halfWidth, games_active: player.n_active, games_missed: player.n_missed },
      note: `Published support: ${player.n_active} active games and ${player.n_missed} missed games; source is limited to this player's tenure window.`,
      sourcePaths: ["players[].player_name", "players[].team", "players[].win_rate_active", "players[].win_rate_missed", "players[].delta_win_rate", "players[].ci95_offset[1]", "players[].n_active", "players[].n_missed"],
    }];
  }).sort((left, right) => right.values.win_rate_difference! - left.values.win_rate_difference! || left.label.localeCompare(right.label));
}

export function buildLineupProxyResearch(source: LineupProxySource): ResearchAnalysis[] {
  const analysisRows = rows(source || {});
  const activeFloor = finite(source?.floors?.min_active) ? source.floors.min_active : null;
  const missedFloor = finite(source?.floors?.min_missed) ? source.floors.min_missed : null;
  const confound = typeof source?.confound === "string" ? source.confound : "The source confound statement is unavailable.";
  return [{
    id: "lineup-proxy-active-missed-record",
    title: "Team record with a player active versus missed",
    sport: "nba",
    category: "Lineup context",
    source: "ctx_lineup_proxy",
    description: "Published player tenure windows compare the team's recorded win rate while each player was active and while that player was missed.",
    scope: `${analysisRows.length} published player windows.${activeFloor === null || missedFloor === null ? " Published support floors are unavailable." : ` Source floors are ${activeFloor} active games and ${missedFloor} missed games.`} Source as-of: ${typeof source?.as_of === "string" ? source.as_of : "unpublished"}. Each row keeps both support counts.`,
    caveat: `${confound} Active and missed games are restricted to the player's own tenure window. The Wald interval is descriptive uncertainty for the recorded difference; it does not remove the roster, schedule, injury, or replacement-lineup confounds.`,
    status: "Descriptive tenure subset",
    fields: [f("win_rate_difference", "Active minus missed", "pp", 2), f("win_rate_active", "Win rate active", "percent", 2), f("win_rate_missed", "Win rate missed", "percent", 2), f("wald_95_half_width", "Wald 95% interval half-width", "pp", 2), f("games_active", "Games active", "number", 0), f("games_missed", "Games missed", "number", 0)],
    rows: analysisRows,
    formula: "Active-minus-missed is delta_win_rate. The displayed half-width is the nonnegative endpoint ci95_offset[1]; n_active and n_missed are published support.",
    bindings: [
      { operand: "delta_win_rate", sourcePath: "players[].delta_win_rate", valueKey: "win_rate_difference", label: "Active minus missed" },
      { operand: "ci95_offset[1]", sourcePath: "players[].ci95_offset[1]", valueKey: "wald_95_half_width", label: "Wald 95% interval half-width" },
      { operand: "n_active", sourcePath: "players[].n_active", valueKey: "games_active", label: "Games active" },
      { operand: "n_missed", sourcePath: "players[].n_missed", valueKey: "games_missed", label: "Games missed" },
    ],
    interpretation: "Positive differences mean the recorded active-window rate is higher. Compare the two game counts before comparing players.",
    references: REFERENCES,
    novelty: "Derived analysis",
  }];
}

export function getLineupProxyResearch(): ResearchAnalysis[] {
  return buildLineupProxyResearch(snapshot<LineupProxySource>("ctx_lineup_proxy"));
}
