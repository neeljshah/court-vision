export type NbaFormCoverage = {
  sourcePlayers: number | null;
  retainedPlayers: number | null;
  eligibleMovers: number | null;
  pooledWindows: number | null;
  publishedMoverRows: number | null;
  seasons: string[];
  windowGames: number | null;
  floors: string | null;
  consistent: boolean;
  retainedShare: number | null;
  eligibleShare: number | null;
  excludedBeforeWindow: number | null;
  excludedBeforeMover: number | null;
};

const record = (value: unknown): Record<string, unknown> =>
  value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
const count = (value: unknown): number | null =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null;

export function buildNbaFormCoverage(source: unknown): NbaFormCoverage {
  const root = record(source), input = record(root.input_coverage), method = record(root.methodology);
  const sourcePlayers = count(input.unique_players);
  const retainedPlayers = count(input.players_with_retained_window);
  const eligibleMovers = count(input.movers_eligible);
  const consistent = sourcePlayers !== null && retainedPlayers !== null && eligibleMovers !== null
    && eligibleMovers <= retainedPlayers && retainedPlayers <= sourcePlayers;
  const published = [root.top_movers_risers, root.top_movers_fallers];
  const validLists = published.every(list => Array.isArray(list) && list.every(value =>
    typeof record(value).player_name === "string" && (record(value).player_name as string).trim().length > 0));
  return {
    sourcePlayers, retainedPlayers, eligibleMovers,
    pooledWindows: count(input.pooled_windows),
    publishedMoverRows: validLists ? (published as unknown[][]).reduce((sum, list) => sum + list.length, 0) : null,
    seasons: Array.isArray(method.seasons_pooled)
      ? [...new Set(method.seasons_pooled.filter((value): value is string => typeof value === "string" && /^\d{4}-\d{2}$/.test(value)))] : [],
    windowGames: count(method.window_games) === 0 ? null : count(method.window_games),
    floors: typeof method.floors === "string" && method.floors.trim() ? method.floors.trim() : null,
    consistent,
    retainedShare: consistent && sourcePlayers > 0 ? retainedPlayers / sourcePlayers : null,
    eligibleShare: consistent && retainedPlayers > 0 ? eligibleMovers / retainedPlayers : null,
    excludedBeforeWindow: consistent ? sourcePlayers - retainedPlayers : null,
    excludedBeforeMover: consistent ? retainedPlayers - eligibleMovers : null,
  };
}
