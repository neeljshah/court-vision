type EntityEntry = { key_numbers?: Record<string, unknown>; as_of?: string };

function finite(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function count(value: number): string {
  return value.toLocaleString("en-US", { maximumFractionDigits: 1 });
}

export function entityObservationContext(pack: string, entry: EntityEntry): string | null {
  if (pack !== "nba_players") return null;
  const numbers = entry.key_numbers || {};
  const seasons = numbers.seasons_played;
  const games = numbers.career_games;
  const minutes = numbers.career_minutes;
  if (!finite(seasons) || !finite(games) || !finite(minutes) || !entry.as_of) return null;
  const seasonLabel = seasons === 1 ? "season" : "seasons";
  return `Corpus measurements: ${count(seasons)} ${seasonLabel} in the snapshot, ${count(games)} games, ${count(minutes)} minutes; snapshot ${entry.as_of.slice(0, 10)}`;
}
