import type { ResearchAnalysis, ResearchOperandValue, ResearchRow } from "./researchTypes";

export type ResolvedResearchOperand = {
  label: string;
  value: ResearchOperandValue;
  sourcePath: string;
  resolved: boolean;
};

function publishedValue(row: ResearchRow, valueKey: string): ResearchOperandValue {
  if (Object.prototype.hasOwnProperty.call(row.values, valueKey)) return row.values[valueKey];
  return row.bindingValues?.[valueKey] ?? null;
}

function isResolved(value: ResearchOperandValue): boolean {
  return typeof value === "string" ? value.trim().length > 0 : typeof value === "number" && Number.isFinite(value);
}

export function resolveResearchOperands(analysis: ResearchAnalysis, row: ResearchRow): ResolvedResearchOperand[] {
  return (analysis.bindings || []).map((binding) => {
    const value = publishedValue(row, binding.valueKey);
    return { label: binding.label, value, sourcePath: binding.sourcePath, resolved: isResolved(value) };
  });
}
