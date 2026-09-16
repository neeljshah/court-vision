import { summarizeDistribution } from "./distribution";
import type { LabRow } from "./labTypes";

export type MeasurementPosition = {
  available: boolean;
  total: number;
  measured: number;
  missing: number;
  value: number | null;
  below: number;
  equal: number;
  above: number;
  median: number | null;
  differenceFromMedian: number | null;
};

function finiteValue(row: LabRow, fieldKey: string): number | null {
  const value = row.values[fieldKey];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function cleanDifference(value: number, median: number): number | null {
  const difference = value - median;
  if (!Number.isFinite(difference)) return null;
  if (difference === 0) return 0;
  if (Number.isInteger(difference)) return difference;
  return Number(difference.toPrecision(12));
}

/**
 * Places one selected measurement within an equally weighted descriptive cohort.
 * Counts describe numeric order only; they do not imply that higher or lower is better.
 */
export function summarizeMeasurementPosition(
  rows: LabRow[], fieldKey: string, selected: LabRow,
): MeasurementPosition {
  const distribution = summarizeDistribution(rows, fieldKey);
  const common = {
    total: distribution.total,
    measured: distribution.measured,
    missing: distribution.missing,
    median: distribution.median,
  };
  const matchingRows = rows.filter(row => row.id === selected.id);
  const selectedValue = finiteValue(selected, fieldKey);
  const populationValue = matchingRows.length === 1 ? finiteValue(matchingRows[0], fieldKey) : null;

  if (selectedValue === null || populationValue === null || selectedValue !== populationValue) {
    return {
      available: false,
      ...common,
      value: null,
      below: 0,
      equal: 0,
      above: 0,
      differenceFromMedian: null,
    };
  }

  const values = rows.map(row => finiteValue(row, fieldKey)).filter((value): value is number => value !== null);
  return {
    available: true,
    ...common,
    value: selectedValue,
    below: values.filter(value => value < selectedValue).length,
    equal: values.filter(value => value === selectedValue).length,
    above: values.filter(value => value > selectedValue).length,
    differenceFromMedian: distribution.median === null
      ? null
      : cleanDifference(selectedValue, distribution.median),
  };
}
