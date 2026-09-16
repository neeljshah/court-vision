import { snapshot } from "./labHelpers";

type RecordValue = Record<string, unknown>;
export type DecompositionSide = "model" | "market";

export interface DecompositionRow {
  side: DecompositionSide;
  brier: number | null;
  reliability: number | null;
  resolution: number | null;
  uncertainty: number | null;
  reconstructedBrier: number | null;
  remainder: number | null;
}

export interface DecompositionSport {
  sport: string;
  rows: DecompositionRow[];
}

function record(value: unknown): RecordValue | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as RecordValue : null;
}

function numberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function rowFrom(side: DecompositionSide, value: unknown): DecompositionRow | null {
  const raw = record(value);
  if (!raw) return null;
  const brier = numberOrNull(raw.brier);
  const reconstructedBrier = numberOrNull(raw.reconstructed_brier);
  return {
    side,
    brier,
    reliability: numberOrNull(raw.reliability),
    resolution: numberOrNull(raw.resolution),
    uncertainty: numberOrNull(raw.uncertainty),
    reconstructedBrier,
    remainder: brier === null || reconstructedBrier === null ? null : reconstructedBrier - brier,
  };
}

/** Builds model and market audit rows as separate published populations. */
export function buildScoreDecomposition(value: unknown): DecompositionSport[] {
  const root = record(value);
  const sports = record(root?.sports);
  if (!sports) return [];
  return Object.entries(sports).flatMap(([sport, value]) => {
    const raw = record(value);
    if (!raw) return [];
    const rows = (["model", "market"] as const)
      .map(side => rowFrom(side, raw[`${side}_prob`]))
      .filter((item): item is DecompositionRow => item !== null);
    return rows.length ? [{ sport, rows }] : [];
  });
}

export function formatDecompositionValue(value: number | null): string {
  return value === null ? "Not published" : value.toFixed(6);
}

/** Reads the build-time JSON snapshot; no browser fetch is used. */
export function loadScoreDecomposition(): DecompositionSport[] {
  return buildScoreDecomposition(snapshot<unknown>("murphy_decomposition"));
}
