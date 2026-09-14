import type { Sport } from "./dashboardTypes";
export type LabField = { key: string; label: string; unit: "number" | "percent" | "pp" | "hours" | "mph"; digits?: number };
export type LabRow = { id: string; label: string; group: string; values: Record<string, number | null>; note?: string };
export type LabDataset = { id: string; title: string; sport: Sport; category: string; source: string; description: string; scope: string; caveat: string; status: string; fields: LabField[]; rows: LabRow[] };
export type NovelCard = { stat_name: string; abbrev: string; module: string; formula: string; prior_art_verdict: string; headline: string; is_honest_null?: boolean };
export type LabData = { datasets: LabDataset[]; novel: NovelCard[] };
export function displayMeasurement(value: number | null, field: LabField) {
  if (value === null || !Number.isFinite(value)) return "Unavailable";
  const scaled = field.unit === "percent" || field.unit === "pp" ? value * 100 : value;
  const suffix = { percent: "%", pp: " pp", hours: " h", mph: " mph", number: "" }[field.unit];
  return scaled.toLocaleString("en-US", { maximumFractionDigits: field.digits ?? 2 }) + suffix;
}
export function rankedRows(rows: LabRow[], field: string, ascending: boolean) {
  return rows.filter(r => r.values[field] !== null && Number.isFinite(r.values[field])).sort((a, b) => {
    const difference = (a.values[field]! - b.values[field]!) * (ascending ? 1 : -1);
    return difference || a.label.localeCompare(b.label);
  });
}
