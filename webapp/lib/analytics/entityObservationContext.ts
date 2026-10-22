type EntityEntry = { key_numbers?: Record<string, unknown>; as_of?: string };

export const MLB_BATTER_SUPPORT_NOTE = "Sample definition: the count covers rows with recorded exit velocity, excluding missing values. Official batted-ball events and foul inclusion are not established. Estimated wOBA on contact uses separately filtered rows; its sample count is not published.";

function finite(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function count(value: number): string {
  return value.toLocaleString("en-US", { maximumFractionDigits: 1 });
}

export function entityObservationContext(pack: string, entry: EntityEntry): string | null {
  if (pack === "mlb_batters") return MLB_BATTER_SUPPORT_NOTE;
  if (pack === "tennis") {
    return "ATP surface windows: source corpus documented as 2015-2025; career uses all dated corpus matches, while recent starts 2023-01-01 and overlaps the corpus. Published floors apply independently for each metric and window. Exact player match counts and latest match dates are not published. The as-of date records claim computation, not a match cutoff.";
  }
  if (pack !== "nba_players") return null;
  const numbers = entry.key_numbers || {};
  const seasons = numbers.seasons_played;
  const games = numbers.career_games;
  const minutes = numbers.career_minutes;
  if (!finite(seasons) || !finite(games) || !finite(minutes) || !entry.as_of) return null;
  const seasonLabel = seasons === 1 ? "season" : "seasons";
  return `Corpus measurements: ${count(seasons)} ${seasonLabel} in the snapshot, ${count(games)} games, ${count(minutes)} minutes; snapshot ${entry.as_of.slice(0, 10)}`;
}
