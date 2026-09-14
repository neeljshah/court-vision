import { field as f, snapshot, type SourceRow } from "./labHelpers";
import type { LabRow } from "./labTypes";
import type { ResearchAnalysis, ResearchReference } from "./researchTypes";

const REFERENCES: ResearchReference[] = [
  { title: "NBA Stats glossary", url: "https://www.nba.com/stats/help/glossary" },
  { title: "NBA team home split", url: "https://www.nba.com/stats/teams/traditional?Location=Home&TeamID=0" },
];
const n = (v: unknown): number | null => typeof v === "number" && Number.isFinite(v) ? v : null;
const calc = (xs: Array<number | null>, fn: (...v: number[]) => number): number | null => {
  if (!xs.every(v => v !== null)) return null;
  const result = fn(...xs as number[]);
  return Number.isFinite(result) ? result : null;
};
const row = (id: string, label: string, group: string, values: Record<string, number | null>, note?: string): LabRow => ({ id, label, group, values, note });
const analysis = (base: Omit<ResearchAnalysis, "sport" | "references" | "novelty">): ResearchAnalysis => ({
  ...base, sport: "nba", references: REFERENCES, novelty: "Derived analysis",
});
type VenueStat = { home_mean: number; away_mean: number; delta: number; rel_delta_pct: number };
type Shooting = { home_pct: number; away_pct: number; delta_pp: number };
type Distribution = { n_players: number; mean_delta: number; std_delta: number; p10_delta: number; median_delta: number; p90_delta: number; share_positive: number };
type VenueSnapshot = {
  input_coverage: { rows_valid: number; unique_players: number; n_home_rows: number; n_away_rows: number; seasons_with_venue_flag: string[] };
  by_season: Record<string, { coverage: { n_rows: number; n_home: number; n_away: number }; league_shooting_pct: Record<string, Shooting>; player_distribution: Distribution }>;
  pooled: { league_deltas: Record<string, VenueStat> };
};
const SHOOTING_LABELS: Record<string, string> = { fg_pct: "Field goal", fg3_pct: "Three-point", ft_pct: "Free throw" };
const BOX_LABELS: Record<string, string> = {
  pts: "Points", reb: "Rebounds", oreb: "Offensive rebounds", dreb: "Defensive rebounds", ast: "Assists",
  stl: "Steals", blk: "Blocks", tov: "Turnovers", pf: "Personal fouls", fga: "Field-goal attempts",
  fg3a: "Three-point attempts", fta: "Free-throw attempts", fgm: "Field goals made",
  fg3m: "Three-pointers made", ftm: "Free throws made",
};

export function getBasketballDepthResearch(): ResearchAnalysis[] {
  const venue = snapshot<VenueSnapshot>("home_away_anatomy");
  const seasons = Object.entries(venue.by_season);
  const shootingRows = seasons.flatMap(([season, value]) => Object.entries(value.league_shooting_pct).map(([metric, s]) =>
    row(`${season}-${metric}`, SHOOTING_LABELS[metric] ?? metric, season, {
      home_pct: s.home_pct / 100, away_pct: s.away_pct / 100, gap: s.delta_pp / 100,
      home_rows: value.coverage.n_home, away_rows: value.coverage.n_away,
    }, "Percentages pool makes and attempts within venue; row support is player-game coverage, not shot attempts.")));

  const venueStatRows = Object.entries(venue.pooled.league_deltas).filter(([key]) => key !== "min").map(([key, s]) =>
    row(`pooled-${key}`, BOX_LABELS[key] ?? key, "Pooled player-game means", {
      relative_gap: s.rel_delta_pct / 100, raw_gap: s.delta, home_mean: s.home_mean, away_mean: s.away_mean,
      home_rows: venue.input_coverage.n_home_rows, away_rows: venue.input_coverage.n_away_rows,
    }, "Unweighted player-game appearance means; counting stats are not pace- or minutes-adjusted."));

  const dispersionRows = seasons.map(([season, value]) => { const d = value.player_distribution; return row(`dispersion-${season}`, season, "Qualified player home-minus-away PPG", {
    middle_80_span: d.p90_delta - d.p10_delta, p10: d.p10_delta, median: d.median_delta, p90: d.p90_delta,
    mean: d.mean_delta, std: d.std_delta, positive_share: d.share_positive, players: d.n_players,
  }, "Each player has at least 15 games at home and 15 away in that season."); });

  const box = snapshot<{ methodology: { minutes_floor_total: number; seasons_pooled: string[] }; input_coverage: { players_meeting_minutes_floor: number }; top_30: SourceRow[] }>("box_value_index");
  const roleRows = box.top_30.map((r, i) => { const pts = n(r.pts_per36), reb = n(r.reb_per36), ast = n(r.ast_per36); const total = calc([pts, reb, ast], (a, b, c) => a + b + c); return row(`role-${i}`, String(r.player_name), "Published box-index top 30", {
    scoring_share: calc([pts, total], (a, b) => b === 0 ? NaN : a / b), rebound_share: calc([reb, total], (a, b) => b === 0 ? NaN : a / b),
    assist_share: calc([ast, total], (a, b) => b === 0 ? NaN : a / b), pra_per36: total, pts_per36: pts, reb_per36: reb, ast_per36: ast,
    minutes: n(r.total_min), games: n(r.games),
  }, "Role shares describe the PTS+REB+AST total only; they are not shares of possessions or player value."); });

  const context = snapshot<{ method: { players: string; cell_min_games: number }; players: SourceRow[] }>("ctx_player_splits");
  const contextRows = context.players.map((r, i) => {
    const splits = r.splits as Record<string, Record<string, unknown>>;
    const defense = n(splits.opp_def_tier.delta_ts_pct), home = n(splits.home_away.delta_ts_pct), rest = n(splits.rest.delta_ts_pct);
    const support = (dimension: string, a: string, b: string) => calc([
      n((splits[dimension][a] as SourceRow).n), n((splits[dimension][b] as SourceRow).n),
    ], Math.min);
    return row(`context-${i}`, String(r.player_name), "Top 50 by total minutes", {
      largest_abs_gap: calc([defense, home, rest], (a, b, c) => Math.max(Math.abs(a), Math.abs(b), Math.abs(c))),
      defense_gap: defense, home_gap: home, rest_gap: rest, mean_abs_gap: n(r.context_sensitivity_score), overall_ts: n(r.overall_ts_pct),
      defense_min_n: support("opp_def_tier", "top10_def", "bottom10_def"), home_min_n: support("home_away", "home", "away"), rest_min_n: support("rest", "b2b", "rest2plus"), games: n(r.total_games),
    }, "Signed gaps follow the source order: top-minus-bottom defense, home-minus-away, and back-to-back minus 2+ days rest.");
  });

  const venueScope = `${venue.input_coverage.rows_valid.toLocaleString("en-US")} valid player-games across ${venue.input_coverage.seasons_with_venue_flag.join(", ")}.`;
  return [
    analysis({ id: "nba-venue-shooting-gap", title: "How does shooting percentage differ by venue?", category: "Venue context", source: "home_away_anatomy", description: "Keeps home and away shooting percentages beside their signed difference for each season.", scope: `${venueScope} Nine season-by-shot-type rows.`, caveat: "Raw completed-game splits do not adjust players, minutes, opponent, rest, pace or shot quality. Player-game support is not the percentage denominator.", status: "Descriptive", fields: [f("gap", "Home minus away", "pp", 3), f("home_pct", "Home", "percent", 3), f("away_pct", "Away", "percent", 3), f("home_rows", "Home player-games", "number", 0), f("away_rows", "Away player-games", "number", 0)], rows: shootingRows, formula: "venue shooting gap = pooled home makes/home attempts - pooled away makes/away attempts", interpretation: "Positive values mean the observed home shooting percentage was higher in that season and shot category." }),
    analysis({ id: "nba-venue-box-profile", title: "Which box-score rates differ most by venue?", category: "Venue context", source: "home_away_anatomy", description: "Compares pooled home and away player-game means across traditional counting categories.", scope: `${venueScope} Fifteen counting-stat rows; minutes excluded from the ranking.`, caveat: "Unweighted appearance means can shift with player mix and playing time. Categories have different scales, so use relative gap for cross-stat comparison.", status: "Descriptive", fields: [f("relative_gap", "Relative home-away gap", "percent", 3), f("raw_gap", "Raw home-away gap", "number", 4), f("home_mean", "Home mean", "number", 4), f("away_mean", "Away mean", "number", 4), f("home_rows", "Home player-games", "number", 0), f("away_rows", "Away player-games", "number", 0)], rows: venueStatRows, formula: "raw gap = home player-game mean - away mean; relative gap = raw gap / away mean", interpretation: "The signed relative gap puts differently scaled box-score categories on a common descriptive axis." }),
    analysis({ id: "nba-player-venue-dispersion", title: "How dispersed are player home-road scoring splits?", category: "Venue context", source: "home_away_anatomy", description: "Shows the center and middle 80% of qualified players' home-minus-away points-per-game differences by season.", scope: `${venueScope} Player floor is 15 games on each side within season.`, caveat: "The qualified population changes by season. Extreme player splits can reflect role, roster, opponent mix and sampling variation; this is not home-court skill.", status: "Descriptive", fields: [f("middle_80_span", "P90-P10 span"), f("p10", "10th percentile"), f("median", "Median"), f("p90", "90th percentile"), f("mean", "Mean"), f("std", "Standard deviation"), f("positive_share", "Positive share", "percent"), f("players", "Qualified players", "number", 0)], rows: dispersionRows, formula: "player gap = home PPG - away PPG; middle-80 span = P90 gap - P10 gap", interpretation: "The span describes between-player dispersion while the median and positive share retain direction." }),
    analysis({ id: "nba-pra-role-composition", title: "How is each published player's PRA composed?", category: "Player roles", source: "box_value_index", description: "Decomposes each published top-30 player's per-36 PTS+REB+AST total into transparent role shares.", scope: `Published top 30 of ${box.input_coverage.players_meeting_minutes_floor} players above ${box.methodology.minutes_floor_total} pooled minutes, ${box.methodology.seasons_pooled.join(", ")}.`, caveat: "Selected on a separate hand-weighted box index, so this is not a league-wide role sample. The source has a known diacritic name-join split, including duplicate Jokic rows.", status: "Descriptive subset", fields: [f("scoring_share", "Scoring share of PRA", "percent"), f("rebound_share", "Rebound share of PRA", "percent"), f("assist_share", "Assist share of PRA", "percent"), f("pra_per36", "PRA / 36"), f("pts_per36", "PTS / 36"), f("reb_per36", "REB / 36"), f("ast_per36", "AST / 36"), f("minutes", "Minutes"), f("games", "Games", "number", 0)], rows: roleRows, formula: "PRA/36 = PTS/36 + REB/36 + AST/36; each role share = role rate / PRA/36", interpretation: "Shares describe how the three box-score components divide the published PRA total, without assigning value weights." }),
    analysis({ id: "nba-context-ts-dominant-gap", title: "Which observed context has the widest TS% gap?", category: "Player context", source: "ctx_player_splits", description: "Keeps three signed true-shooting splits beside the largest absolute gap for each high-minute player.", scope: `${context.method.players}; all 50 published players have three usable dimensions and at least ${context.method.cell_min_games} games per cell.`, caveat: "These are raw associations. Defense tiers use points allowed per game; venue and rest splits do not control opponents, role, injuries, season or attempts. Largest-gap selection is descriptive and upward-selected.", status: "Descriptive subset", fields: [f("largest_abs_gap", "Largest absolute gap", "pp", 2), f("defense_gap", "Top-minus-bottom defense", "pp", 2), f("home_gap", "Home minus away", "pp", 2), f("rest_gap", "B2B minus 2+ days", "pp", 2), f("mean_abs_gap", "Mean absolute gap", "pp", 2), f("overall_ts", "Overall TS%", "percent", 2), f("defense_min_n", "Defense min cell", "number", 0), f("home_min_n", "Venue min cell", "number", 0), f("rest_min_n", "Rest min cell", "number", 0), f("games", "Games", "number", 0)], rows: contextRows, formula: "largest absolute gap = max(abs(top10-defense TS - bottom10-defense TS), abs(home TS - away TS), abs(B2B TS - 2+ days TS))", interpretation: "The component with the largest magnitude is the widest observed split in this corpus, not an estimated cause or future effect." }),
  ];
}
