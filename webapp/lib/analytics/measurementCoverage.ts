import type { LabField, LabRow } from "./labTypes";

export type MeasurementCoverage = {
  key: string;
  label: string;
  total: number;
  measured: number;
  missing: number;
  share: number | null;
};

/** Summarizes finite measurement availability with one equal-weight count per row. */
export function summarizeMeasurementCoverage(
  rows: LabRow[], fields: LabField[],
): MeasurementCoverage[] {
  return fields.map(field => {
    const measured = rows.filter(row => {
      const value = row.values[field.key];
      return typeof value === "number" && Number.isFinite(value);
    }).length;
    return {
      key: field.key,
      label: field.label,
      total: rows.length,
      measured,
      missing: rows.length - measured,
      share: rows.length ? measured / rows.length : null,
    };
  });
}
