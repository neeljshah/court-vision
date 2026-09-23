import { field as f, snapshot } from "./labHelpers";
import type { LabRow } from "./labTypes";
import type { ResearchAnalysis, ResearchReference } from "./researchTypes";

export type MatchupRangePair = {
  row: unknown;
  col: unknown;
  n_meetings: unknown;
  mean_total: unknown;
};
export type MatchupRangeSource = {
  input_coverage?: { games_total?: unknown; seasons?: unknown; date_max?: unknown };
  mask?: { min_meetings?: unknown };
  pairings: MatchupRangePair[];
};
export type MatchupRangeTeamAtlas = {
  entries: Array<{ entity: unknown; key_numbers?: { team_full_name?: unknown } }>;
};

const REFERENCES: ResearchReference[] = [{
  title: "Published NBA matchup-grid method",
  url: "https://github.com/neeljshah/court-vision/blob/master/scripts/platformkit/analytics_showcase/nba_matchup_grid.py",
}, {
  title: "Published NBA team-name atlas",
  url: "https://github.com/neeljshah/court-vision/blob/master/webapp/public/data/showcase/atlas_nba_teams_manifest.json",
}];

type Pair = { row: string; col: string; total: number; meetings: number };

function validPair(raw: MatchupRangePair): Pair | null {
  const row = typeof raw.row === "string" ? raw.row.trim() : "";
  const col = typeof raw.col === "string" ? raw.col.trim() : "";
  const total = raw.mean_total;
  const meetings = raw.n_meetings;
  if (!row || !col || row === col || typeof total !== "number" || !Number.isFinite(total) || total < 0 ||
      typeof meetings !== "number" || !Number.isSafeInteger(meetings) || meetings <= 0) return null;
  return { row, col, total, meetings };
}

function compatiblePairs(raw: MatchupRangePair[], minimum: number): Pair[] {
  const candidates = new Map<string, Pair[]>();
  for (const item of raw) {
    const pair = validPair(item);
    if (!pair || pair.meetings < minimum) continue;
    const key = `${pair.row}\u0000${pair.col}`;
    candidates.set(key, [...(candidates.get(key) || []), pair]);
  }
  const unique = new Map<string, Pair>();
  for (const [key, values] of candidates) {
    if (values.every(value => value.total === values[0].total && value.meetings === values[0].meetings)) unique.set(key, values[0]);
  }
  return [...unique.values()].filter(pair => {
    const reverse = unique.get(`${pair.col}\u0000${pair.row}`);
    return reverse?.total === pair.total && reverse.meetings === pair.meetings;
  });
}

function teamNames(atlas?: MatchupRangeTeamAtlas): Map<string, string> {
  const candidates = new Map<string, Set<string>>();
  for (const entry of atlas?.entries || []) {
    const code = typeof entry.entity === "string" ? entry.entity.trim() : "";
    const rawName = entry.key_numbers?.team_full_name;
    const name = typeof rawName === "string" ? rawName.trim() : "";
    if (!code || !name) continue;
    const names = candidates.get(code) || new Set<string>();
    names.add(name);
    candidates.set(code, names);
  }
  return new Map([...candidates].flatMap(([code, names]) => names.size === 1 ? [[code, [...names][0]] as const] : []));
}

function matchupSummary(pairs: Pair[]): { mean: number | null; sd: number | null; meetings: number | null } {
  const meetings = pairs.reduce((sum, pair) => sum + pair.meetings, 0);
  const weightedTotal = pairs.reduce((sum, pair) => sum + pair.meetings * pair.total, 0);
  if (!Number.isSafeInteger(meetings) || meetings <= 0) return { mean: null, sd: null, meetings: null };
  if (!Number.isFinite(weightedTotal)) return { mean: null, sd: null, meetings };
  if (pairs.every(pair => pair.total === pairs[0].total)) return { mean: pairs[0].total, sd: 0, meetings };
  const mean = weightedTotal / meetings;
  if (!Number.isFinite(mean)) return { mean: null, sd: null, meetings };
  const squared = pairs.reduce((sum, pair) => sum + pair.meetings * ((pair.total - mean) ** 2), 0);
  const sd = Math.sqrt(squared / meetings);
  return { mean, sd: Number.isFinite(sd) ? sd : null, meetings };
}

function rangeRows(source: MatchupRangeSource, names: Map<string, string>): LabRow[] {
  const byTeam = new Map<string, Pair[]>();
  const rawMinimum = source.mask?.min_meetings;
  if (typeof rawMinimum !== "number" || !Number.isInteger(rawMinimum) || rawMinimum < 2) return [];
  const minimum = rawMinimum;
  for (const pair of compatiblePairs(source.pairings, minimum)) byTeam.set(pair.row, [...(byTeam.get(pair.row) || []), pair]);
  return [...byTeam].sort(([a], [b]) => a.localeCompare(b)).flatMap(([team, pairs]) => {
    const distinct = new Map(pairs.map(pair => [pair.col, pair]));
    const ordered = [...distinct.values()].sort((a, b) => a.total - b.total || a.col.localeCompare(b.col));
    if (ordered.length < 2) return [];
    const low = ordered[0];
    const high = ordered.find(pair => pair.total === ordered[ordered.length - 1].total)!;
    const lowTies = ordered.filter(pair => pair.total === low.total);
    const highTies = ordered.filter(pair => pair.total === high.total);
    const summary = matchupSummary(ordered);
    const endpoints = (pairs: Pair[]) => pairs.map(pair => `${pair.col} (${pair.meetings} meetings)`).join(", ");
    return [{
      id: `matchup-range-${team.toLowerCase()}`,
      label: team,
      group: "Historical opponent range",
      values: {
        total_range: high.total - low.total,
        high_mean_total: high.total,
        low_mean_total: low.total,
        high_meetings: high.meetings,
        low_meetings: low.meetings,
        opponents: ordered.length,
        meeting_weighted_mean_total: summary.mean,
        between_opponent_mean_total_sd: summary.sd,
        meetings_across_pairings: summary.meetings,
      },
      note: `${names.has(team) ? `Team: ${names.get(team)}. ` : ""}Highest opponent endpoint${highTies.length > 1 ? "s" : ""}: ${endpoints(highTies)}. Lowest opponent endpoint${lowTies.length > 1 ? "s" : ""}: ${endpoints(lowTies)}. Numeric meeting fields use the first alphabetic endpoint when tied. Meeting-weighted fields use all ${ordered.length} included opponent pairings.`,
    }];
  });
}

export function buildBasketballMatchupRangeResearch(source: MatchupRangeSource, teamAtlas?: MatchupRangeTeamAtlas): ResearchAnalysis[] {
  const names = teamNames(teamAtlas);
  const rows = rangeRows(source, names);
  const seasons = Array.isArray(source.input_coverage?.seasons)
    ? source.input_coverage.seasons.filter(value => typeof value === "string" && value.trim()).join(", ")
    : "published seasons";
  const games = source.input_coverage?.games_total;
  const minimum = source.mask?.min_meetings;
  const date = source.input_coverage?.date_max;
  const validGames = typeof games === "number" && Number.isInteger(games) && games >= 0 ? games : null;
  const validMinimum = typeof minimum === "number" && Number.isInteger(minimum) && minimum >= 2 ? minimum : null;
  const parsedDate = typeof date === "string" && /^\d{4}-\d{2}-\d{2}$/.test(date) ? Date.parse(`${date}T00:00:00Z`) : NaN;
  const validDate = typeof date === "string" && Number.isFinite(parsedDate) && new Date(parsedDate).toISOString().slice(0, 10) === date ? date : undefined;
  return [{
    id: "nba-opponent-total-range",
    title: "Opponent scoring range by team",
    sport: "nba",
    category: "Matchup explorer",
    source: "nba_matchup_grid",
    description: "For each team, compares its highest and lowest published opponent-specific mean combined point totals and summarizes the included opponent means using their meeting support.",
    scope: `${rows.length} teams derived from the ${validGames === null ? "published input" : `${validGames}-game input corpus`} across ${seasons}${validDate ? `; latest input date ${validDate}` : ""}. ${validMinimum === null ? "Source meeting floor is unavailable or invalid; no rows are included." : `Each endpoint uses at least ${validMinimum} meetings.`}${names.size ? " Team names come separately from atlas_nba_teams_manifest and do not affect matchup values or dates." : ""}`,
    caveat: "These are extrema among opponent means, so the range is selection-sensitive. Seasons and venues are pooled, with no published regular-season or playoff filter; rosters, opponent strength and recency are not adjusted. Team points are reconstructed by summing source player box-score points, without a published completeness audit. Pair means are serialized to two decimals, so weighted results approximate calculations from full raw precision. The between-opponent SD describes differences among included pair means; within-pair variation is not published. Meeting support is a sum of team-meetings across included pairings, not independent observations; adding it across teams counts the same games twice. Endpoint meeting counts differ. The latest input date is not a per-pair cutoff. This describes prior games and is not a forecast.",
    status: "Descriptive",
    fields: [
      f("total_range", "High-low mean-total range"),
      f("high_mean_total", "Highest opponent mean total"),
      f("low_mean_total", "Lowest opponent mean total"),
      f("high_meetings", "Selected high-end pair meetings", "number", 0),
      f("low_meetings", "Selected low-end pair meetings", "number", 0),
      f("opponents", "Opponents represented", "number", 0),
      f("meeting_weighted_mean_total", "Meeting-weighted mean combined total"),
      f("between_opponent_mean_total_sd", "Between-opponent mean-total SD"),
      f("meetings_across_pairings", "Team-meetings across included pairings", "number", 0),
    ],
    rows,
    formula: "Range = max over opponents of mean(row-team points + opponent points per meeting) - min over opponents of that same mean. Meeting-weighted mean = sum(n_i * mean_total_i) / sum(n_i). Between-opponent mean-total SD = sqrt(sum(n_i * (mean_total_i - meeting-weighted mean)^2) / sum(n_i)); this is a population descriptive denominator with no sample correction. Meetings across pairings = sum(n_i) over included opponent rows.",
    interpretation: "The range shows the interval between included opponent means. Read the meeting-weighted mean as their support-weighted center and the SD only as dispersion among those opponent means, alongside the included-pairing count and team-meeting support.",
    references: REFERENCES,
    novelty: "Derived analysis",
  }];
}

export function getBasketballMatchupRangeResearch(): ResearchAnalysis[] {
  return buildBasketballMatchupRangeResearch(
    snapshot<MatchupRangeSource>("nba_matchup_grid"),
    snapshot<MatchupRangeTeamAtlas>("atlas_nba_teams_manifest"),
  );
}
