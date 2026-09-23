export type TennisSurfaceFold = {
  sourceIndex: number;
  fold: number | null;
  testStates: number | null;
  blindBrier: number | null;
  surfaceBrier: number | null;
  delta: number | null;
  sourcePath: string;
};

export type TennisSurfaceFoldGroup = {
  tour: string;
  rows: TennisSurfaceFold[];
};

const TOURS = ["atp", "wta"] as const;

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function safeInteger(value: unknown, minimum: number): number | null {
  return typeof value === "number"
    && Number.isSafeInteger(value)
    && value >= minimum
    ? value
    : null;
}

function brier(value: unknown): number | null {
  return typeof value === "number"
    && Number.isFinite(value)
    && value >= 0
    && value <= 1
    ? value
    : null;
}

function foldRow(value: unknown, tour: string, sourceIndex: number): TennisSurfaceFold {
  const row = record(value);
  const blindBrier = brier(row?.brier_h0);
  const surfaceBrier = brier(row?.brier_h1);
  return {
    sourceIndex,
    fold: safeInteger(row?.fold, 0),
    testStates: safeInteger(row?.n_test, 1),
    blindBrier,
    surfaceBrier,
    delta: blindBrier !== null && surfaceBrier !== null
      ? Number((surfaceBrier - blindBrier).toFixed(12))
      : null,
    sourcePath: `ingame_surface_context.tours.${tour}.n_folds[${sourceIndex}]`,
  };
}

export function buildTennisSurfaceFolds(tours: unknown): TennisSurfaceFoldGroup[] {
  const tourRecord = record(tours);
  return TOURS.map(tour => {
    const tourBlock = record(tourRecord?.[tour]);
    const folds = tourBlock?.n_folds;
    return {
      tour,
      rows: Array.isArray(folds)
        ? folds.map((row, sourceIndex) => foldRow(row, tour, sourceIndex))
        : [],
    };
  });
}
