"use client";

import { summarizeMeasurementPosition } from "@/lib/analytics/measurementPosition";
import { displayMeasurement, type LabField, type LabRow } from "@/lib/analytics/labTypes";

type MeasurementPositionProps = {
  rows: LabRow[];
  field: LabField;
  selected: LabRow;
  populationLabel: string;
};

function rowLabel(count: number) {
  return `${count} ${count === 1 ? "row" : "rows"}`;
}

function signedMeasurement(value: number | null, field: LabField) {
  if (value === null) return "Unavailable";
  const displayField = field.unit === "percent" ? { ...field, unit: "pp" as const } : field;
  return `${value > 0 ? "+" : ""}${displayMeasurement(value, displayField)}`;
}

function PositionBand({ below, equal, above, measured, label }: { below: number; equal: number; above: number; measured: number; label: string }) {
  const segments = [
    { key: "below", count: below, text: "below" },
    { key: "equal", count: equal, text: "tied" },
    { key: "above", count: above, text: "above" },
  ];
  return <div className="measurement-position-band" role="img" aria-label={`${label}: ${rowLabel(below)} below, ${rowLabel(equal)} tied, and ${rowLabel(above)} above the selected value among ${rowLabel(measured)} with measurements.`}>
    {segments.filter(segment => segment.count > 0).map(segment => <span key={segment.key} className={`measurement-position-segment measurement-position-${segment.key}`} style={{ flexGrow: segment.count }} aria-hidden="true" />)}
  </div>;
}

export function MeasurementPosition({ rows, field, selected, populationLabel }: MeasurementPositionProps) {
  const position = summarizeMeasurementPosition(rows, field.key, selected);
  const selectedValue = position.available ? displayMeasurement(position.value, field) : "Unavailable";
  return <section className="measurement-position" aria-label="Measurement context">
    <div className="measurement-position-heading">
      <div><p className="cv-eyebrow">Measurement context</p><h4>Context for {field.label}</h4></div>
      <span>{populationLabel}</span>
    </div>
    <dl className="measurement-position-coverage">
      <div><dt>Reference rows</dt><dd>{rowLabel(position.total)}</dd></div>
      <div><dt>Measured</dt><dd>{position.measured} <small>/ {position.total}</small></dd></div>
      <div><dt>Missing</dt><dd>{rowLabel(position.missing)}</dd></div>
    </dl>
    {position.available ? <>
      <div className="measurement-position-selected"><span>Selected value</span><b>{selectedValue}</b></div>
      <dl className="measurement-position-counts">
        <div><dt>Below selected value</dt><dd>{rowLabel(position.below)}</dd></div>
        <div><dt>Equal to selected value</dt><dd>{rowLabel(position.equal)}</dd></div>
        <div><dt>Above selected value</dt><dd>{rowLabel(position.above)}</dd></div>
      </dl>
      <PositionBand below={position.below} equal={position.equal} above={position.above} measured={position.measured} label={field.label} />
      <dl className="measurement-position-comparison">
        <div><dt>Median</dt><dd>{displayMeasurement(position.median, field)}</dd></div>
        <div><dt>Difference from median</dt><dd>{signedMeasurement(position.differenceFromMedian, field)}</dd></div>
      </dl>
    </> : <p className="measurement-position-unavailable">The selected value is unavailable. Its position and difference from the median are unavailable.</p>}
    <p className="measurement-position-note">Each published row has equal weight. This is a descriptive numeric position, not a quality label. Text search does not change this reference population.</p>
    <details className="measurement-position-method"><summary>Method note</summary><p>Counts use exact raw-value ties: strictly below, equal, and strictly above. The equal count includes the selected row. The median follows the lab's R7 percentile definition. Differences use unrounded values, so they may differ from subtracting the displayed labels. Rows are not independent games or events.</p><a href="https://www.itl.nist.gov/div898/handbook/prc/section2/prc262.htm" target="_blank" rel="noreferrer">NIST percentile definitions</a></details>
  </section>;
}
