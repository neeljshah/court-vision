import { snapshot } from "./labHelpers";

export type ReliabilitySide = "model" | "market";
export type ConfidenceInterval = readonly [number | null, number | null];

export interface ReliabilityBin {
  binLo: number | null;
  binHi: number | null;
  meanP: number | null;
  meanY: number | null;
  meanYCi: ConfidenceInterval;
  gap: number | null;
  gapCi: ConfidenceInterval;
  n: number | null;
  nGames: number | null;
  lowN: boolean;
}

export interface ReliabilityMeta {
  nBoot: number | null;
  ciPct: ConfidenceInterval;
  clusterUnit: string | null;
  minGamesPerBinFloor: number | null;
  asOf: string | null;
  nRows: number | null;
  nGames: number | null;
  lowPower: boolean;
}

export interface ReliabilitySeries {
  sport: string;
  side: ReliabilitySide;
  bins: ReliabilityBin[];
  meta: ReliabilityMeta;
}

type RawRecord = Record<string, unknown>;

function record(value: unknown): RawRecord | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as RawRecord : null;
}

function numberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function interval(value: unknown): ConfidenceInterval {
  if (!Array.isArray(value)) return [null, null];
  return [numberOrNull(value[0]), numberOrNull(value[1])];
}

function sideFor(key: string, entry: RawRecord): ReliabilitySide | null {
  if (entry.label === "model" || key === "model_prob") return "model";
  if (entry.label === "market" || key === "market_prob") return "market";
  return null;
}

function binFrom(value: unknown): ReliabilityBin | null {
  const raw = record(value);
  if (!raw) return null;
  return {
    binLo: numberOrNull(raw.bin_lo),
    binHi: numberOrNull(raw.bin_hi),
    meanP: numberOrNull(raw.mean_p),
    meanY: numberOrNull(raw.mean_y),
    meanYCi: interval(raw.mean_y_ci),
    gap: numberOrNull(raw.gap),
    gapCi: interval(raw.gap_ci),
    n: numberOrNull(raw.n),
    nGames: numberOrNull(raw.n_games),
    lowN: raw.low_n === true,
  };
}

/** Builds chart-ready reliability series from the committed calibration snapshot. */
export function buildCalibrationReliability(value: unknown): ReliabilitySeries[] {
  const root = record(value);
  const sports = record(root?.sports);
  if (!root || !sports) return [];

  const shared = {
    nBoot: numberOrNull(root.n_boot),
    ciPct: interval(root.ci_pct),
    clusterUnit: typeof root.cluster_unit === "string" ? root.cluster_unit : null,
    minGamesPerBinFloor: numberOrNull(root.min_games_per_bin_floor),
    asOf: typeof root.as_of === "string" ? root.as_of : null,
  };

  return Object.entries(sports).flatMap(([sport, sportValue]) => {
    const sportEntry = record(sportValue);
    const sides = record(sportEntry?.sides);
    if (!sportEntry || !sides) return [];
    const meta: ReliabilityMeta = {
      ...shared,
      nRows: numberOrNull(sportEntry.n_rows),
      nGames: numberOrNull(sportEntry.n_games),
      lowPower: sportEntry.low_power === true,
    };
    return Object.entries(sides).flatMap(([key, sideValue]) => {
      const sideEntry = record(sideValue);
      const side = sideEntry ? sideFor(key, sideEntry) : null;
      if (!sideEntry || !side) return [];
      const bins = Array.isArray(sideEntry.bins) ? sideEntry.bins.map(binFrom).filter((bin): bin is ReliabilityBin => bin !== null) : [];
      return [{ sport, side, bins, meta }];
    });
  });
}

/** Reads the build-time JSON snapshot; no browser fetch is used. */
export function loadCalibrationReliability(): ReliabilitySeries[] {
  return buildCalibrationReliability(snapshot<unknown>("calibration_stability"));
}
