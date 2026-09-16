import type { LabDefinition, LabRow } from "./labTypes";

export type LabCohort = { key: string; label: string; definition: LabDefinition; rowCount: number };
export type LabComparisonPolicy = { compatible: boolean; cohorts: LabCohort[]; reason: string };

const fields = ["unit", "clockField", "threshold", "season"] as const;
const fieldLabels = { unit: "score units", clockField: "clock fields", threshold: "score thresholds", season: "seasons" };
const present = (value: unknown): value is string | number => value !== undefined && value !== null && value !== "";

function valueKey(definition: LabDefinition) {
  return fields.map(field => present(definition[field]) ? `${field}=${definition[field]}` : "").filter(Boolean).join("|") || "published-rows";
}

function cohortLabel(definition: LabDefinition) {
  const parts = [definition.sport, present(definition.threshold) ? `${definition.threshold} ${definition.unit || ""}`.trim() : undefined, definition.clockField, definition.season].filter(present);
  return parts.join(" / ") || "Published rows";
}

export function labComparisonPolicy(rows: LabRow[]): LabComparisonPolicy {
  const definitions = rows.map(row => row.definition || {});
  const differing = fields.filter(field => new Set(definitions.map(definition => definition[field]).filter(present)).size > 1);
  const byKey = new Map<string, LabCohort>();
  rows.forEach(row => {
    const definition = row.definition || {};
    const key = valueKey(definition);
    const existing = byKey.get(key);
    if (existing) existing.rowCount += 1;
    else byKey.set(key, { key, label: cohortLabel(definition), definition, rowCount: 1 });
  });
  const compatible = differing.length === 0;
  return {
    compatible,
    cohorts: [...byKey.values()],
    reason: compatible ? "Published definitions are consistent across these rows." : `Rows differ by ${differing.map(field => fieldLabels[field]).join(" and ")}.`,
  };
}
