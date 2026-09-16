import type { LabDefinition, LabRow } from "./labTypes";

export type LabCompatibility = "compatible" | "incompatible" | "unknown";
export type LabCohort = { key: string; label: string; definition: LabDefinition; rowCount: number; missingDefinition: boolean };
export type LabComparisonPolicy = { compatibility: LabCompatibility; compatible: boolean; cohorts: LabCohort[]; reason: string };

const fields = ["unit", "clockField", "threshold", "season"] as const;
const fieldLabels = { unit: "score units", clockField: "clock fields", threshold: "score thresholds", season: "seasons" };
const present = (value: unknown): value is string | number => value !== undefined && value !== null && value !== "";
const missingDefinition = (row: LabRow) => !row.definition || Object.keys(row.definition).length === 0;

function valueKey(definition: LabDefinition, missingDefinition: boolean) {
  if (missingDefinition) return "missing-definition";
  return fields.map(field => present(definition[field]) ? `${field}=${definition[field]}` : "").filter(Boolean).join("|") || "published-rows";
}

function cohortLabel(definition: LabDefinition) {
  const parts = [definition.sport, present(definition.threshold) ? `${definition.threshold} ${definition.unit || ""}`.trim() : undefined, definition.clockField, definition.season].filter(present);
  return parts.join(" / ") || "Published rows";
}

export function matchesLabCohort(row: LabRow, cohort: LabCohort) {
  if (cohort.missingDefinition) return missingDefinition(row);
  return !missingDefinition(row) && fields.every(field => row.definition?.[field] === cohort.definition[field]);
}

export function labComparisonPolicy(rows: LabRow[]): LabComparisonPolicy {
  const definitions = rows.map(row => row.definition || {});
  const differing = fields.filter(field => new Set(definitions.map(definition => definition[field]).filter(present)).size > 1);
  const byKey = new Map<string, LabCohort>();
  rows.forEach(row => {
    const definition = row.definition || {};
    const missing = missingDefinition(row);
    const key = valueKey(definition, missing);
    const existing = byKey.get(key);
    if (existing) existing.rowCount += 1;
    else byKey.set(key, { key, label: missing ? "Definition not published" : cohortLabel(definition), definition, rowCount: 1, missingDefinition: missing });
  });
  const hasMissingDefinition = rows.some(missingDefinition);
  const compatibility: LabCompatibility = hasMissingDefinition ? "unknown" : differing.length ? "incompatible" : "compatible";
  return {
    compatibility,
    compatible: compatibility === "compatible",
    cohorts: [...byKey.values()],
    reason: compatibility === "compatible" ? "Published definitions are consistent across these rows."
      : compatibility === "unknown" ? "One or more published rows do not include a cohort definition, so compatibility is unknown."
      : `Rows differ by ${differing.map(field => fieldLabels[field]).join(" and ")}.`,
  };
}
