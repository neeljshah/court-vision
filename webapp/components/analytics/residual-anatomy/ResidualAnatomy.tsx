"use client";

import { useEffect, useState } from "react";
import { Receipt } from "@/components/analytics/Receipt";
import { readResidualAnatomyViewState, residualAnatomyViewSearch, type ResidualAnatomyViewState } from "@/lib/analytics/inspectorViewState";
import type { ResidualAnatomyData, ResidualMetric, ResidualSegment, ResidualSport } from "@/lib/analytics/residualAnatomy";

const METRICS: Array<{ key: ResidualMetric; label: string }> = [
  { key: "n", label: "Rows" },
  { key: "meanAbsResidual", label: "Mean absolute residual" },
  { key: "totalAbsResidualMass", label: "Sum of absolute forecast errors" },
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

function metricValue(segment: ResidualSegment, metric: ResidualMetric): number {
  if (metric === "n") return segment.n ?? 0;
  if (metric === "meanAbsResidual") return segment.meanAbsResidual;
  return segment.totalAbsResidualMass;
}

function scaleStep(value: number, maximum: number): number {
  return Math.min(4, Math.max(0, Math.round((maximum ? value / maximum : 0) * 4)));
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

function Inspector({ segment }: { segment: ResidualSegment }) {
  return <aside id="ra-selected-segment" className="ra-inspector" aria-live="polite" aria-label="Selected residual segment">
    <p>Selected segment</p><h2>{sportLabel(segment.sport)}: {segmentLabel(segment)}</h2>
    <dl><div><dt>n</dt><dd>{count(segment.n)}</dd></div><div><dt>mean_abs_residual</dt><dd>{residual(segment.meanAbsResidual)}</dd></div><div><dt>total_abs_residual_mass</dt><dd>{mass(segment.totalAbsResidualMass)}</dd></div></dl>
    <p className="ra-worked">This published segment contains {count(segment.n)} rows. Its per-row absolute error is {residual(segment.meanAbsResidual)}; the published sum of absolute forecast errors across those rows is {mass(segment.totalAbsResidualMass)}.</p>
  </aside>;
}

export function ResidualAnatomy({ data }: { data: ResidualAnatomyData }) {
  const defaults = { sport: data.sports[0]?.segments[0]?.sport || data.sports[0]?.sport || "", time: data.sports[0]?.segments[0]?.timeBucket || "", prob: data.sports[0]?.segments[0]?.probBucket || "", metric: "totalAbsResidualMass" as ResidualMetric };
  const [view, setView] = useState<ResidualAnatomyViewState>(defaults);
  const [restored, setRestored] = useState(false);
  const selectedMetric = METRICS.find(item => item.key === view.metric)?.label || "Metric";

  useEffect(() => {
    const restore = () => { setView(readResidualAnatomyViewState(window.location.search, data)); setRestored(true); };
    restore();
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, [data]);

  useEffect(() => {
    if (!restored) return;
    const url = new URL(window.location.href);
    const search = residualAnatomyViewSearch(url.search, view, data);
    window.history.replaceState(window.history.state, "", `${url.pathname}${search ? `?${search}` : ""}${url.hash}`);
  }, [data, restored, view]);

  if (!data.sports.length) return <p className="ra-empty">No published residual segments are available in this snapshot.</p>;

  return <section className="ra-shell" aria-label="Residual anatomy explorer">
    <div className="ra-controls" aria-label="Residual metric">
      <span>Cell measure</span>
      <div>{METRICS.map(item => <button key={item.key} type="button" aria-pressed={view.metric === item.key} onClick={() => setView(current => ({ ...current, metric: item.key }))}>{item.label}</button>)}</div>
    </div>
    {data.sports.map(sport => {
      const selected = view.sport === sport.sport ? sport.segments.find(item => item.timeBucket === view.time && item.probBucket === view.prob) : undefined;
      const metricMaximum = Math.max(0, ...sport.segments.map(item => metricValue(item, view.metric)));
      return <section className="ra-sport" key={sport.sport} aria-labelledby={`${sport.sport}-residual-title`}>
      <header className="ra-sport-head">
        <div><p>Forecasts grouped by game state</p><h2 id={`${sport.sport}-residual-title`}>{sportLabel(sport.sport)}</h2></div>
        <dl><div><dt>n_records</dt><dd>{count(sport.nRecords)}</dd></div><div><dt>n_skipped</dt><dd>{count(sport.nSkipped)}</dd></div></dl>
      </header>
      <div className="ra-selected-view">
      <div className="ra-grid-wrap" role="region" aria-label={`${sportLabel(sport.sport)} residual grid`} data-scroll-region>
        <p className="ra-scale-legend">Sequential scale: 0 to {view.metric === "n" ? count(metricMaximum) : view.metric === "meanAbsResidual" ? residual(metricMaximum) : mass(metricMaximum)} for {selectedMetric}; blank cells: no published segment.</p>
        <table className="ra-grid"><caption>{sportLabel(sport.sport)} time bucket by probability bucket. Blank cells have no published segment.</caption><thead><tr><th scope="col">Time bucket</th>{sport.probBuckets.map(bucket => <th scope="col" key={bucket}>{bucket}</th>)}</tr></thead><tbody>{sport.grid.map(row => <tr key={row.timeBucket}><th scope="row">{row.timeBucket}</th>{row.cells.map((segment, index) => {
          const selected = segment?.sport === view.sport && segment.timeBucket === view.time && segment.probBucket === view.prob;
          const step = segment ? scaleStep(metricValue(segment, view.metric), metricMaximum) : 0;
          return <td className={segment ? undefined : "ra-cell-missing"} key={`${row.timeBucket}-${sport.probBuckets[index]}`}>{segment ? <button type="button" className={`${selected ? "ra-cell-selected " : ""}ra-cell-seq-${step}`} aria-pressed={selected} aria-controls="ra-selected-segment" aria-label={`${sportLabel(sport.sport)} ${segmentLabel(segment)} ${selectedMetric}`} onClick={() => setView(current => ({ ...current, sport: segment.sport, time: segment.timeBucket, prob: segment.probBucket }))}>{metricText(segment, view.metric)}{selected && <span className="ra-selected-mark">Selected</span>}</button> : null}</td>;
        })}</tr>)}</tbody></table>
      </div>
      {selected && <Inspector segment={selected} />}
      </div>
      <Rankings sport={sport} />
    </section>;
    })}
    <p className="ra-source-fields">Source fields: residual_anatomy.json -&gt; sports[sport].segments[] -&gt; time_bucket, prob_bucket, n, mean_abs_residual, total_abs_residual_mass; sports[sport] -&gt; n_records, n_skipped.</p>
    {data.exclusions.length > 0 && <p className="ra-exclusions">Excluded corpora: {data.exclusions.map(item => `${item.sport}: ${item.reason}`).join("; ")}</p>}
    <div className="ra-receipt"><Receipt sourceArtifact="public/data/showcase/residual_anatomy.json" label="descriptive_only" verdict="descriptive_only" /></div>
  </section>;
}

export default ResidualAnatomy;
