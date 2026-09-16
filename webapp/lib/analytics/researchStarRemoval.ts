import { field as f, snapshot } from "./labHelpers";
import type { ResearchAnalysis, ResearchReference, ResearchRow } from "./researchTypes";

type StarTeam = { team_abbr?: unknown; player_name?: unknown; p_win_with?: unknown; p_win_without?: unknown; delta_winprob?: unknown; on_off_net_rating_delta?: unknown; min_on?: unknown };
export type StarRemovalSource = { as_of?: unknown; teams?: unknown; caveat?: unknown };

const REFERENCES: ResearchReference[] = [{
  title: "Published star-removal formulation",
  url: "https://github.com/neeljshah/court-vision/blob/master/scripts/platformkit/analytics_showcase/cf_star_removal.py",
}];
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const probability = (value: unknown): value is number => finite(value) && value >= 0 && value <= 1;
const asDate = (value: unknown): string | undefined => typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(`${value}T00:00:00Z`)) ? value : undefined;

function rows(source: StarRemovalSource): ResearchRow[] {
  if (!Array.isArray(source.teams)) return [];
  return (source.teams as StarTeam[]).flatMap((team) => {
    const abbr = typeof team.team_abbr === "string" ? team.team_abbr.trim() : "";
    const player = typeof team.player_name === "string" ? team.player_name.trim() : "";
    if (!abbr || !player || !probability(team.p_win_with) || !probability(team.p_win_without) || !finite(team.delta_winprob) || !finite(team.on_off_net_rating_delta) || !finite(team.min_on) || team.min_on < 0) return [];
    return [{
      id: `star-removal-${abbr.toLowerCase()}-${player.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`,
      label: `${player} (${abbr})`,
      group: "Published team scenario",
      values: { win_probability_with: team.p_win_with, win_probability_without: team.p_win_without, win_probability_difference: team.delta_winprob, on_off_net_rating_delta: team.on_off_net_rating_delta, minutes_active: team.min_on },
      note: `Published player-on support: ${team.min_on} minutes. Source caveat: roster confounding is not controlled.`,
      sourcePaths: ["teams[].player_name", "teams[].team_abbr", "teams[].p_win_with", "teams[].p_win_without", "teams[].delta_winprob", "teams[].on_off_net_rating_delta", "teams[].min_on"],
    }];
  }).sort((left, right) => left.label.localeCompare(right.label));
}

export function buildStarRemovalResearch(source: StarRemovalSource): ResearchAnalysis[] {
  const analysisRows = rows(source || {});
  return [{
    id: "star-removal-team-win-probability",
    title: "Team win probability with and without a lead player",
    sport: "nba",
    category: "Counterfactual context",
    source: "cf_star_removal",
    description: "For each team, the published scenario compares its listed win probability with and without the designated player.",
    scope: `${analysisRows.length} published team-player scenarios. Player-on minutes are retained as the available support measure.`,
    caveat: "The published scenario carries roster confounding. This scenario does not isolate the player's causal contribution.",
    status: "Descriptive scenario",
    fields: [f("win_probability_difference", "With minus without", "pp", 2), f("win_probability_with", "Win probability with player", "percent", 2), f("win_probability_without", "Win probability without player", "percent", 2), f("on_off_net_rating_delta", "Published on-off net-rating delta"), f("minutes_active", "Player-on minutes", "number", 1)],
    rows: analysisRows,
    formula: "With-minus-without is the published delta_winprob field; the probability and support fields are copied from the same team scenario.",
    interpretation: "Larger positive differences indicate a wider gap in this published scenario. Read the player-on minutes and source caveat alongside every row.",
    references: REFERENCES,
    novelty: "Experimental formulation",
    asOf: asDate(source?.as_of),
  }];
}

export function getStarRemovalResearch(): ResearchAnalysis[] {
  return buildStarRemovalResearch(snapshot<StarRemovalSource>("cf_star_removal"));
}
