"use client";

import { ChevronRight } from "lucide-react";
import { displayMeasurement as display, type LabField } from "@/lib/analytics/labTypes";
import type { summarizeScatter } from "@/lib/analytics/scatterSummary";

type Props = {
  data: ReturnType<typeof summarizeScatter>;
  x: LabField;
  y: LabField;
};

function rowCount(count: number) {
  return `${count} ${count === 1 ? "row" : "rows"}`;
}

export function ScatterSummary({ data, x, y }: Props) {
  const counts = [
    ["Both measurements", data.paired],
    ["Horizontal only", data.xOnly],
    ["Vertical only", data.yOnly],
    ["Neither measurement", data.neither],
  ] as const;
  return <section className="scatter-summary" aria-label="Paired measurement summary">
    <div className="scatter-summary-heading"><h3>What the plot includes</h3><p><b>{data.paired} / {data.total}</b> rows plotted</p></div>
    <p className="scatter-summary-scope">Counts follow the current search and population. A point requires both measurements on the same published row.</p>
    <dl className="scatter-availability">{counts.map(([label, count]) => <div key={label}><dt>{label}</dt><dd>{count}</dd></div>)}</dl>
    {x.key === y.key && <p className="scatter-same-field">Both axes use the same measurement. The diagonal reflects that choice.</p>}
    <details className="scatter-median-details">
      <summary><ChevronRight aria-hidden="true" size={13} /> Compare medians and calculation</summary>
      <div className="scatter-median-fields">{([{ axis: "Horizontal", field: x, values: data.x }, { axis: "Vertical", field: y, values: data.y }]).map(({ axis, field, values }) => <section key={axis} aria-label={`${axis} measurement medians`}>
        <p className="cv-eyebrow">{axis} / {field.label}</p>
        <dl><div><dt>Plotted-row median</dt><dd>{display(values.pairedMedian, field)}<small>{rowCount(data.paired)} with both measurements</small></dd></div><div><dt>All available-row median</dt><dd>{display(values.allMedian, field)}<small>{rowCount(values.measured)} with this measurement</small></dd></div></dl>
      </section>)}</div>
      <p>Each median uses the current search and population with equal weight per row. The plotted-row median uses only complete pairs; the all available-row median also includes rows missing the other measurement. An empty set has no median. No missing value is filled.</p>
      <p>These are descriptive subsets, not independent game counts. Source windows can differ. Pair availability does not establish comparability, causality, or prediction quality.</p>
      <a href="https://www.itl.nist.gov/div898/handbook/eda/section3/scatterp.htm" target="_blank" rel="noreferrer">How to read a scatter plot</a>
    </details>
  </section>;
}
