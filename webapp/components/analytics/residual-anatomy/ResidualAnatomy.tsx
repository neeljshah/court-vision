"use client";

import { useState } from "react";
import { Receipt } from "@/components/analytics/Receipt";
import type { ResidualAnatomyData, ResidualMetric, ResidualSegment, ResidualSport } from "@/lib/analytics/residualAnatomy";

const METRICS: Array<{ key: ResidualMetric; label: string }> = [
  { key: "n", label: "Rows" },
  { key: "meanAbsResidual", label: "Mean absolute residual" },
  { key: "totalAbsResidualMass", label: "Total absolute residual mass" },
];

function sportLabel(sport: string): string {
  return sport === "mlb" ? "MLB" : sport === "soccer_intl" ? "International soccer" : sport.replace(/_/g, " ");
}

function count(value: number | null): string {
  return value === null ? "Not published" : value.toLocaleString("en-US");
}

function residual(value: number): string {
  return value.toFixed(4);
}

function mass(value: number): string {
  return value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function metricText(segment: ResidualSegment, metric: ResidualMetric): string {
  if (metric === "n") return count(segment.n);
  if (metric === "meanAbsResidual") return residual(segment.meanAbsResidual);
  return mass(segment.totalAbsResidualMass);
}

function segmentLabel(segment: ResidualSegment): string {
  return `${segment.timeBucket}, ${segment.probBucket}`;
}

function Rankings({ sport }: { sport: ResidualSport }) {
  const volume = sport.rankings.byVolume.slice(0, 3);
  const perRow = sport.rankings.byPerRowError.slice(0, 3);
  return <div className="ra-rankings" aria-label={`${sportLabel(sport.sport)} rankings`}>
    <section>
      <h3>Recorded volume</h3>
      <ol>{volume.map(segment => <li key={`volume-${segmentLabel(segment)}`}><span>{segmentLabel(segment)}</span><strong>{mass(segment.totalAbsResidualMass)}</strong></li>)}</ol>
    </section>
    <section>
      <h3>Per-row absolute residual</h3>
      <ol>{perRow.map(segment => <li key={`per-row-${segmentLabel(segment)}`}><span>{segmentLabel(segment)}</span><strong>{residual(segment.meanAbsResidual)}</strong></li>)}</ol>
    </section>
  </div>;
}

export function ResidualAnatomy({ data }: { data: ResidualAnatomyData }) {
  const [metric, setMetric] = useState<ResidualMetric>("totalAbsResidualMass");
  const [selected, setSelected] = useState<ResidualSegment | null>(data.sports[0]?.segments[0] || null);
  const selectedMetric = METRICS.find(item => item.key === metric)?.label || "Metric";

  if (!data.sports.length) return <p className="ra-empty">No published residual segments are available in this snapshot.</p>;

  return <section className="ra-shell" aria-label="Residual anatomy explorer">
    <div className="ra-controls" aria-label="Residual metric">
      <span>Cell measure</span>
      <div>{METRICS.map(item => <button key={item.key} type="button" aria-pressed={metric === item.key} onClick={() => setMetric(item.key)}>{item.label}</button>)}</div>
    </div>
    {data.sports.map(sport => <section className="ra-sport" key={sport.sport} aria-labelledby={`${sport.sport}-residual-title`}>
      <header className="ra-sport-head">
        <div><p>Published segmentation</p><h2 id={`${sport.sport}-residual-title`}>{sportLabel(sport.sport)}</h2></div>
        <dl><div><dt>n_records</dt><dd>{count(sport.nRecords)}</dd></div><div><dt>n_skipped</dt><dd>{count(sport.nSkipped)}</dd></div></dl>
      </header>
      <div className="ra-grid-wrap" role="region" aria-label={`${sportLabel(sport.sport)} residual grid`} data-scroll-region>
        <table className="ra-grid"><caption>{sportLabel(sport.sport)} time bucket by probability bucket. Blank cells have no published segment.</caption><thead><tr><th scope="col">Time bucket</th>{sport.probBuckets.map(bucket => <th scope="col" key={bucket}>{bucket}</th>)}</tr></thead><tbody>{sport.grid.map(row => <tr key={row.timeBucket}><th scope="row">{row.timeBucket}</th>{row.cells.map((segment, index) => <td key={`${row.timeBucket}-${sport.probBuckets[index]}`}>{segment ? <button type="button" aria-label={`${sportLabel(sport.sport)} ${segmentLabel(segment)} ${selectedMetric}`} onClick={() => setSelected(segment)}>{metricText(segment, metric)}</button> : null}</td>)}</tr>)}</tbody></table>
      </div>
      <Rankings sport={sport} />
    </section>)}
    {selected && <aside className="ra-inspector" aria-live="polite" aria-label="Selected residual segment">
      <p>Selected segment</p><h2>{sportLabel(selected.sport)}: {segmentLabel(selected)}</h2>
      <dl><div><dt>n</dt><dd>{count(selected.n)}</dd></div><div><dt>mean_abs_residual</dt><dd>{residual(selected.meanAbsResidual)}</dd></div><div><dt>total_abs_residual_mass</dt><dd>{mass(selected.totalAbsResidualMass)}</dd></div></dl>
    </aside>}
    <p className="ra-source-fields">Source fields: residual_anatomy.json -&gt; sports[sport].segments[] -&gt; time_bucket, prob_bucket, n, mean_abs_residual, total_abs_residual_mass; sports[sport] -&gt; n_records, n_skipped.</p>
    {data.exclusions.length > 0 && <p className="ra-exclusions">Excluded corpora: {data.exclusions.map(item => `${item.sport}: ${item.reason}`).join("; ")}</p>}
    <div className="ra-receipt"><Receipt sourceArtifact="public/data/showcase/residual_anatomy.json" label="descriptive_only" verdict="descriptive_only" /></div>
  </section>;
}

export default ResidualAnatomy;
