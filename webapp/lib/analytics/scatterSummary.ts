import { summarizeDistribution } from "./distribution";
import type { LabRow } from "./labTypes";

export type ScatterAxisSummary = {
  measured: number;
  pairedMedian: number | null;
  allMedian: number | null;
};

export type ScatterSummary = {
  total: number;
  paired: number;
  xOnly: number;
  yOnly: number;
  neither: number;
  pairedRows: LabRow[];
  x: ScatterAxisSummary;
  y: ScatterAxisSummary;
};

function isMeasured(row: LabRow, key: string): boolean {
  const value = row.values[key];
  return typeof value === "number" && Number.isFinite(value);
}

/** Summarizes paired availability without changing row order or weighting. */
export function summarizeScatter(rows: LabRow[], xKey: string, yKey: string): ScatterSummary {
  const pairedRows: LabRow[] = [];
  let xOnly = 0;
  let yOnly = 0;
  let neither = 0;

  for (const row of rows) {
    const hasX = isMeasured(row, xKey);
    const hasY = isMeasured(row, yKey);
    if (hasX && hasY) pairedRows.push(row);
    else if (hasX) xOnly++;
    else if (hasY) yOnly++;
    else neither++;
  }

  const paired = pairedRows.length;
  return {
    total: rows.length,
    paired,
    xOnly,
    yOnly,
    neither,
    pairedRows,
    x: {
      measured: paired + xOnly,
      pairedMedian: summarizeDistribution(pairedRows, xKey).median,
      allMedian: summarizeDistribution(rows, xKey).median,
    },
    y: {
      measured: paired + yOnly,
      pairedMedian: summarizeDistribution(pairedRows, yKey).median,
      allMedian: summarizeDistribution(rows, yKey).median,
    },
  };
}
