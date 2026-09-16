export type DependenceSideName = "model" | "market";

export type DependenceSide = {
  side: DependenceSideName;
  values: number[];
  nGames: number;
  skipped: { lowN: number; flat: number };
  median: number | null;
  shareAbovePointNine: number | null;
};

export type DependenceSport = {
  sport: string;
  nRecords: number | null;
  nSeries: number | null;
  sides: DependenceSide[];
};

type UnknownRecord = Record<string, unknown>;

function record(value: unknown): UnknownRecord | null {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as UnknownRecord : null;
}

function number(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function integer(value: unknown): number {
  const parsed = number(value);
  return parsed !== null && parsed >= 0 ? Math.trunc(parsed) : 0;
}

function values(value: unknown): number[] {
  return Array.isArray(value) ? value.filter((item): item is number => typeof item === "number" && Number.isFinite(item)) : [];
}

export function median(input: number[]): number | null {
  if (!input.length) return null;
  const ordered = [...input].sort((a, b) => a - b);
  const middle = Math.floor(ordered.length / 2);
  const value = ordered.length % 2 ? ordered[middle] : (ordered[middle - 1] + ordered[middle]) / 2;
  return Number(value.toFixed(6));
}

export function shareAbovePointNine(input: number[]): number | null {
  return input.length ? Number((input.filter((value) => value > 0.9).length / input.length).toFixed(6)) : null;
}

function parseSide(name: DependenceSideName, source: UnknownRecord): DependenceSide | null {
  const arrays = record(source.autocorr_values);
  const summary = record(source[name]);
  if (!arrays || !summary || !Array.isArray(arrays[name])) return null;
  const skipped = record(summary.skipped);
  const series = values(arrays[name]);
  return {
    side: name,
    values: series,
    nGames: integer(summary.n_games),
    skipped: { lowN: integer(skipped?.low_n), flat: integer(skipped?.flat) },
    median: median(series),
    shareAbovePointNine: shareAbovePointNine(series),
  };
}

export function buildObservationDependence(input: unknown): DependenceSport[] {
  const root = record(input);
  const sports = record(root?.sports);
  if (!sports) return [];
  return Object.entries(sports).flatMap(([sport, entry]) => {
    const source = record(entry);
    if (!source) return [];
    const sides = (["model", "market"] as const).flatMap((name) => {
      const side = parseSide(name, source);
      return side ? [side] : [];
    });
    return sides.length ? [{ sport, nRecords: number(source.n_records), nSeries: number(source.n_series), sides }] : [];
  });
}
