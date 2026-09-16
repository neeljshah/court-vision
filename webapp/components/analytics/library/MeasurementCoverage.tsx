"use client";

import { useId } from "react";
import { ChevronRight } from "lucide-react";
import { summarizeMeasurementCoverage } from "@/lib/analytics/measurementCoverage";
import type { LabField, LabRow } from "@/lib/analytics/labTypes";

type MeasurementCoverageProps = {
  rows: LabRow[];
  fields: LabField[];
  selectedKey: string;
  populationLabel: string;
  onSelect: (key: string) => void;
};

function fieldLabel(available: number, total: number) {
  return `${available} / ${total} ${total === 1 ? "field has" : "fields have"} values`;
}

function rowLabel(count: number) {
  return `${count} ${count === 1 ? "row" : "rows"}`;
}

export function MeasurementCoverage({ rows, fields, selectedKey, populationLabel, onSelect }: MeasurementCoverageProps) {
  const entries = summarizeMeasurementCoverage(rows, fields);
  const availableFields = entries.filter(entry => entry.measured > 0).length;
  const emptyPopulation = rows.length === 0;
  const descriptionPrefix = useId();
  return <details className="measurement-coverage">
    <summary><ChevronRight aria-hidden="true" size={13} /><span>Measurement availability</span><small>{fieldLabel(availableFields, entries.length)}</small>{emptyPopulation && <em>No published rows</em>}</summary>
    <section className="measurement-coverage-panel" aria-label="Measurement availability">
      <p className="measurement-coverage-population">Reference population: <b>{populationLabel}</b>. {rowLabel(rows.length)} published.</p>
      {emptyPopulation && <p className="measurement-coverage-empty">No published rows are available in this reference population. Field selection remains available.</p>}
      <p className="measurement-coverage-search">Text search does not change this reference population.</p>
      <div className="measurement-coverage-fields">
        {entries.map((entry, index) => <button key={entry.key} type="button" aria-label={`Use ${entry.label}`} aria-describedby={`${descriptionPrefix}-field-${index}`} aria-pressed={selectedKey === entry.key} onClick={() => onSelect(entry.key)}>
          <span className="measurement-coverage-field-label">{entry.label}</span>
          <span id={`${descriptionPrefix}-field-${index}`} className="measurement-coverage-count">{entry.measured} / {entry.total} measured; {entry.missing} missing</span>
          {entry.share !== null && <i className="measurement-coverage-band" aria-hidden="true"><i style={{ width: `${entry.share * 100}%` }} /></i>}
        </button>)}
      </div>
      <p className="measurement-coverage-note">Availability describes published values only. It does not establish data quality or independent game counts, and measurement windows can differ.</p>
    </section>
  </details>;
}
