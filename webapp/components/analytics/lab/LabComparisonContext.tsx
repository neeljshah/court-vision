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
  ].filter(([, values]) => values.length) as [string, string[]][];
  if (!definitions.length) return null;
  return <section className="lab-definition" aria-label="Published definition"><p className="cv-eyebrow">Published definition</p><dl>{definitions.map(([label, values]) => <div key={label}><dt>{label}</dt><dd>{values.join("; ")}</dd></div>)}</dl></section>;
}
