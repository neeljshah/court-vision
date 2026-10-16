import { field as f, snapshot } from "./labHelpers";
import type { ResearchAnalysis, ResearchReference, ResearchRow } from "./researchTypes";

type Player = { rank?: unknown; player_id?: unknown; player_name?: unknown; net_rating_delta?: unknown; min_on?: unknown };
type Season = { top_15?: unknown; bottom_15?: unknown; min_sample?: { min_on?: unknown } };
export type OnOffSource = { seasons?: unknown };

const REFERENCES: ResearchReference[] = [{
  title: "Published NBA on-off method",
  url: "https://github.com/neeljshah/court-vision/blob/master/scripts/platformkit/analytics_showcase/on_off_showcase.py",
}];
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const seasonLabel = (season: string) => season.replace("_", "-");

function rows(source: OnOffSource): ResearchRow[] {
  if (!source.seasons || typeof source.seasons !== "object" || Array.isArray(source.seasons)) return [];
  return Object.entries(source.seasons as Record<string, unknown>).flatMap(([season, value]) => {
    const entry = value as Season;
    const lists = [["top_15", entry.top_15], ["bottom_15", entry.bottom_15]] as const;
    return lists.flatMap(([list, players]) => {
      if (!Array.isArray(players)) return [];
      return (players as Player[]).flatMap((player, index) => {
        if (!finite(player.rank) || !finite(player.player_id) || typeof player.player_name !== "string" || !player.player_name || !finite(player.net_rating_delta) || !finite(player.min_on) || player.min_on < 0) return [];
        return [{
          id: `on-off-${season}-${list}-${player.player_id}-${index}`,
          label: `${seasonLabel(season)} | ${player.player_name}`,
          group: seasonLabel(season),
          values: { net_rating_delta: player.net_rating_delta, minutes_on_court: player.min_on, published_rank: player.rank },
          note: `${list === "top_15" ? "Upper" : "Lower"} published selection. The season's stated on-court floor is ${finite(entry.min_sample?.min_on) ? entry.min_sample.min_on : "unpublished"} minutes.`,
          sourcePaths: [`seasons.${season}.${list}[].player_name`, `seasons.${season}.${list}[].net_rating_delta`, `seasons.${season}.${list}[].min_on`, `seasons.${season}.${list}[].rank`],
        }];
      });
    });
  }).sort((left, right) => left.group.localeCompare(right.group) || right.values.net_rating_delta! - left.values.net_rating_delta! || left.label.localeCompare(right.label));
}

export function buildOnOffResearch(source: OnOffSource): ResearchAnalysis[] {
  const analysisRows = rows(source || {});
  return [{
    id: "nba-on-off-net-rating-by-player",
    title: "NBA on/off margin delta per 48 minutes",
    sport: "nba",
    category: "Player context",
    source: "on_off_showcase",
    question: "How does the team's scoring margin per 48 minutes differ with each selected NBA player on and off court?",
    method: "Restate the source's upper and lower 15-player selections for each season with on/off margin delta per 48 minutes, on-court minutes, and published rank.",
    description: "Published upper and lower player selections show the on/off difference in team scoring margin per 48 minutes, with the source's on-court minutes.",
    scope: `${analysisRows.length} published player selections across the available NBA seasons. The source does not publish an as-of timestamp.`,
    caveat: "The source labels these on-off readings roster-confounded: teammate mix, opponent strength, coach usage, and game context are not controlled. They describe the published seasons and do not isolate a causal player effect.",
    status: "Descriptive player-context subset",
    fields: [f("net_rating_delta", "On/off margin delta per 48", "number", 3), f("minutes_on_court", "Minutes on court", "number", 2), f("published_rank", "Published rank", "number", 0)],
    rows: analysisRows,
    formula: "net_rating_delta = net_rating_on_per48 - net_rating_off_per48: team point differential per 48 minutes with the player on court minus the corresponding off-court rate. Values are copied from the published net_rating_delta field. Minutes on court is copied from min_on; off-court minutes are not published in these selected rows.",
    interpretation: "Positive values mean the team's scoring margin per 48 minutes was higher with the player on court than off court. Read this difference with on-court minutes and the source selection; players outside the published selections are not shown.",
    references: REFERENCES,
    novelty: "Derived analysis",
  }];
}

export function getOnOffResearch(): ResearchAnalysis[] {
  return buildOnOffResearch(snapshot<OnOffSource>("on_off_showcase"));
}
