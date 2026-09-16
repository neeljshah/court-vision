import type { LabDefinition, LabRow } from "./labTypes";

export type LabCompatibility = "compatible" | "incompatible" | "unknown";
type DefinitionField = "sport" | "population" | "observationWindow" | "unit" | "clockField" | "threshold" | "season";
export type LabCohort = {
  key: string;
  label: string;
  definition: LabDefinition;
  rowCount: number;
  missingDefinition: boolean;
  compatibility: LabCompatibility;
  fields: DefinitionField[];
};
export type LabComparisonPolicy = { compatibility: LabCompatibility; compatible: boolean; cohorts: LabCohort[]; reason: string };

const fields: DefinitionField[] = ["sport", "population", "observationWindow", "unit", "clockField", "threshold", "season"];
const fieldLabels: Record<DefinitionField, string> = {
  sport: "sports", population: "populations", observationWindow: "observation windows", unit: "score units",
  clockField: "clock fields", threshold: "score thresholds", season: "seasons",
};
const present = (value: unknown): value is string | number => value !== undefined && value !== null && value !== "";

function publishedFields(rows: LabRow[]) {
  return fields.filter(field => rows.some(row => present(row.definition?.[field])));
}

function completeDefinition(row: LabRow, definitionFields: DefinitionField[]) {
  return definitionFields.length > 0 && definitionFields.every(field => present(row.definition?.[field]));
}

function valueKey(definition: LabDefinition, definitionFields: DefinitionField[], complete: boolean) {
  if (!complete) return "missing-definition";
  return definitionFields.map(field => `${field}=${definition[field]}`).join("|");
}

function cohortLabel(definition: LabDefinition) {
  const parts = [definition.sport, present(definition.threshold) ? `${definition.threshold} ${definition.unit || ""}`.trim() : undefined, definition.clockField, definition.season, definition.observationWindow, definition.population].filter(present);
  return parts.join(" / ") || "Published rows";
}

export function matchesLabCohort(row: LabRow, cohort: LabCohort) {
  if (cohort.compatibility === "unknown") return !completeDefinition(row, cohort.fields);
  return completeDefinition(row, cohort.fields) && cohort.fields.every(field => row.definition?.[field] === cohort.definition[field]);
}

export function labComparisonPolicy(rows: LabRow[]): LabComparisonPolicy {
  const definitionFields = publishedFields(rows);
  const incompleteRows = rows.some(row => !completeDefinition(row, definitionFields));
  const differing = definitionFields.filter(field => new Set(rows.map(row => row.definition?.[field]).filter(present)).size > 1);
  const byKey = new Map<string, LabCohort>();
  rows.forEach(row => {
    const definition = row.definition || {};
    const complete = completeDefinition(row, definitionFields);
    const key = valueKey(definition, definitionFields, complete);
    const existing = byKey.get(key);
    if (existing) existing.rowCount += 1;
    else byKey.set(key, {
      key,
      label: complete ? cohortLabel(definition) : "Definition not published",
      definition,
      rowCount: 1,
      missingDefinition: !complete,
      compatibility: complete ? "compatible" : "unknown",
      fields: definitionFields,
    });
  });
  const compatibility: LabCompatibility = incompleteRows ? "unknown" : differing.length ? "incompatible" : "compatible";
  const cohorts = [...byKey.values()].sort((left, right) => Number(left.compatibility !== "compatible") - Number(right.compatibility !== "compatible"));
  return {
    compatibility,
    compatible: compatibility === "compatible",
    cohorts,
    reason: compatibility === "compatible" ? "Published definitions are consistent across these rows."
      : compatibility === "unknown" ? "One or more published rows omit a required cohort field, so compatibility is unknown."
      : `Rows differ by ${differing.map(field => fieldLabels[field]).join(" and ")}.`,
  };
}
