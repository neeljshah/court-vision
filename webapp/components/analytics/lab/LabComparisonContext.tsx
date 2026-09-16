import type { LabRow } from "@/lib/analytics/labTypes";

const valuesFor = (rows: LabRow[], value: (row: LabRow) => string | undefined) =>
  Array.from(new Set(rows.map(value).filter((item): item is string => Boolean(item))));

export function LabComparisonContext({ rows }: { rows: LabRow[] }) {
  const definitions = [
    ["Sport", valuesFor(rows, row => row.definition?.sport)],
    ["Score threshold", valuesFor(rows, row => row.definition?.threshold !== undefined ? `${row.definition.threshold} ${row.definition.unit || ""}`.trim() : undefined)],
    ["Unit", valuesFor(rows, row => row.definition?.unit)],
    ["Clock unit", valuesFor(rows, row => row.definition?.clockField)],
    ["Season", valuesFor(rows, row => row.definition?.season)],
    ["Population", valuesFor(rows, row => row.definition?.population)],
    ["Observation window", valuesFor(rows, row => row.definition?.observationWindow)],
  ] as [string, string[]][];
  const required = new Set(["Sport", "Population", "Observation window"]);
  const visible = definitions.filter(([label, values]) => required.has(label) || values.length);
  return <section className="lab-definition" aria-label="Published definition"><p className="cv-eyebrow">Published definition</p><dl>{visible.map(([label, values]) => <div key={label}><dt>{label}</dt><dd>{values.length ? values.join("; ") : "Not published"}</dd></div>)}</dl></section>;
}
