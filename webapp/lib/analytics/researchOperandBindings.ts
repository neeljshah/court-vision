import type { ResearchAnalysis, ResearchOperandValue, ResearchRow } from "./researchTypes";

export type ResolvedResearchOperand = {
  label: string;
  value: ResearchOperandValue;
  sourcePath: string;
  rowSourcePath?: string;
  resolved: boolean;
};

function exactRowPath(schemaPath: string, paths: string[] = []): string | undefined {
  // These display paths are not a general query language. Unsupported syntax stays literal.
  const property = "(?:[A-Za-z0-9_][A-Za-z0-9_-]*|[0-9]+-[0-9]+\\+)";
  const schemaPart = `(?:${property}|\\*)(?:\\[\\d*\\])*`;
  const exactPart = `${property}(?:\\[\\d+\\])*`;
  if (!new RegExp(`^${schemaPart}(?:\\.${schemaPart})*$`).test(schemaPath)) return undefined;
  if (!schemaPath.includes("*") && !schemaPath.includes("[]")) return undefined;
  const escape = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const pattern = schemaPath.split("[]").map(part => part.split("*").map(escape).join(property)).join("\\[\\d+\\]");
  const match = new RegExp(`^${pattern}$`);
  const concrete = new RegExp(`^${exactPart}(?:\\.${exactPart})*$`);
  const candidates = [...new Set(paths.filter(path => concrete.test(path) && match.test(path)))];
  return candidates.length === 1 ? candidates[0] : undefined;
}

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
    const rowSourcePath = exactRowPath(binding.sourcePath, row.sourcePaths);
    return { label: binding.label, value, sourcePath: binding.sourcePath, resolved: isResolved(value), ...(rowSourcePath ? { rowSourcePath } : {}) };
  });
}
