import type { LabField } from "@/lib/analytics/labTypes";
import type { ResearchRow } from "@/lib/analytics/researchTypes";
import { displayMeasurement } from "@/lib/analytics/labTypes";

type Operand = { path: string; label: string; value: string };

const SOURCE_FIELD_ALIASES: Record<string, string> = {
  outcome_rate: "leading_side_outcome_share",
  n_games: "games",
  n_ticks: "ticks",
  delta_win_rate: "win_rate_difference",
  "ci95_offset1": "wald_95_half_width",
  n_active: "games_active",
  n_missed: "games_missed",
  fav_strength_at_ref_pace: "reference_favorite_probability",
  fav_win_prob: "favorite_win_probability",
  upset_prob: "trailing_win_probability",
  p_win_with: "win_probability_with",
  p_win_without: "win_probability_without",
  delta_winprob: "win_probability_difference",
  min_on: "minutes_active",
};

function readable(path: string): string {
  const field = path.split(".").at(-1)?.replace(/\[\]/g, "") || path;
  return field.replace(/_/g, " ").replace(/\b\w/g, letter => letter.toUpperCase());
}

function normalized(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]/g, "");
}

function fieldFor(path: string, fields: LabField[]): LabField | undefined {
  const leaf = normalized(path.split(".").at(-1) || path);
  const alias = SOURCE_FIELD_ALIASES[leaf];
  return fields.find(field => {
    const key = normalized(field.key);
    const label = normalized(field.label);
    return key === alias || key === leaf || label === leaf || (key.length > 3 && (key.includes(leaf) || leaf.includes(key)));
  });
}

function contextValue(path: string, row: ResearchRow): string | undefined {
  const leaf = normalized(path.split(".").at(-1) || path);
  if (leaf === "playername" || leaf === "leadband" || leaf === "teamabbr") return row.label;
  if (leaf === "team" || leaf === "timeband") return row.group;
  if (leaf === "maskednlt30") return /small-support source cell/i.test(row.note || "") ? "true" : "false";
  return undefined;
}

function operands(row: ResearchRow, fields: LabField[]): Operand[] {
  return (row.sourcePaths || []).map((path) => {
    const field = fieldFor(path, fields);
    return { path, label: readable(path), value: field ? displayMeasurement(row.values[field.key], field) : contextValue(path, row) || "Unavailable" };
  });
}

function substitutedFormula(formula: string, row: ResearchRow, fields: LabField[]): string {
  return fields.reduce((output, field) => {
    const value = displayMeasurement(row.values[field.key], field);
    // One alternation per field, longest term first, and never re-substitute a term that
    // already carries its "(value)" suffix (label and key can be the same word).
    const terms = Array.from(new Set([field.label, field.key.replace(/_/g, " ")].map((term) => term.toLowerCase())))
      .sort((left, right) => right.length - left.length)
      .map((term) => term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
    const pattern = new RegExp(`\\b(${terms.join("|")})\\b(?!\\s\\()`, "gi");
    return output.replace(pattern, (match) => `${match} (${value})`);
  }, formula);
}

export function ResearchProvenance({ row, fields, formula, resultField }: { row: ResearchRow; fields: LabField[]; formula: string; resultField: LabField }) {
  if (!row.sourcePaths?.length) return null;
  const result = displayMeasurement(row.values[resultField.key], resultField);
  return <section className="research-provenance" aria-label="Calculation inputs">
    <p className="cv-eyebrow">Calculation inputs</p>
    <dl>{operands(row, fields).map((operand) => <div key={operand.path}><dt>{operand.label}</dt><dd>{operand.value}</dd><details><summary>Source path</summary><code>{operand.path}</code></details></div>)}</dl>
    <p className="research-provenance-result"><strong>{resultField.label}: {result}</strong><span>{substitutedFormula(formula, row, fields)}</span></p>
  </section>;
}
