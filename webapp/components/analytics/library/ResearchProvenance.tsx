import type { LabField } from "@/lib/analytics/labTypes";
import { displayMeasurement } from "@/lib/analytics/labTypes";
import { resolveResearchOperands, type ResolvedResearchOperand } from "@/lib/analytics/researchOperandBindings";
import type { ResearchAnalysis, ResearchRow } from "@/lib/analytics/researchTypes";

function readable(path: string): string {
  const field = path.split(".").at(-1)?.replace(/\[\]/g, "") || path;
  return field.replace(/_/g, " ").replace(/\b\w/g, letter => letter.toUpperCase());
}

function bindingFor(analysis: ResearchAnalysis, operand: ResolvedResearchOperand) {
  return analysis.bindings?.find(item => item.label === operand.label && item.sourcePath === operand.sourcePath);
}

function operandValue(operand: ResolvedResearchOperand, fields: LabField[], analysis: ResearchAnalysis): string {
  if (typeof operand.value === "string") return operand.value;
  const field = fields.find(item => item.key === bindingFor(analysis, operand)?.valueKey);
  return field ? displayMeasurement(operand.value, field) : String(operand.value);
}

function escaped(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function substitutedFormula(formula: string, operands: ResolvedResearchOperand[], fields: LabField[], analysis: ResearchAnalysis): string {
  return operands.reduce((output, operand) => {
    const term = bindingFor(analysis, operand)?.operand;
    if (!term) return output;
    const pattern = new RegExp(`(?<![A-Za-z0-9_])${escaped(term)}(?![A-Za-z0-9_]|\\s\\()`, "gi");
    return output.replace(pattern, match => `${match} (${operandValue(operand, fields, analysis)})`);
  }, formula);
}

export function ResearchProvenance({ analysis, row, fields, resultField }: { analysis: ResearchAnalysis; row: ResearchRow; fields: LabField[]; resultField: LabField }) {
  if (!row.sourcePaths?.length) return null;
  const operands = resolveResearchOperands(analysis, row);
  const allResolved = operands.length > 0 && operands.every(operand => operand.resolved);
  const result = displayMeasurement(row.values[resultField.key], resultField);
  return <section className="research-provenance" aria-label="Calculation inputs">
    <p className="cv-eyebrow">Calculation inputs</p>
    {operands.length > 0 ? <dl>{operands.map(operand => <div key={operand.sourcePath}><dt>{operand.label}</dt><dd>{operand.resolved ? operandValue(operand, fields, analysis) : "not published for this row"}<details><summary>Source path</summary><code>{operand.sourcePath}</code></details></dd></div>)}</dl> : <dl>{row.sourcePaths.map(path => <div key={path}><dt>{readable(path)}</dt><dd><details open><summary>Source path</summary><code>{path}</code></details></dd></div>)}</dl>}
    <p className="research-provenance-result"><strong>{resultField.label}: {result}</strong><span>{allResolved ? substitutedFormula(analysis.formula, operands, fields, analysis) : analysis.formula}</span></p>
  </section>;
}
