"use client";

import { useState } from "react";
import { stateReliabilityMetricValue, stateReliabilityRow, type StateReliabilityMetric, type StateReliabilitySource, type StateReliabilitySport } from "@/lib/analytics/stateReliability";

const sources: Array<{ id: StateReliabilitySource; label: string }> = [{ id: "model", label: "Model source" }, { id: "market", label: "Reference source" }];
const metrics: Array<{ id: StateReliabilityMetric; label: string }> = [
  { id: "signed-gap", label: "Signed gap (pp)" },
  { id: "absolute-gap", label: "Absolute gap (pp)" },
  { id: "support", label: "Support (n)" },
];

function sportLabel(sport: string): string {
  return sport === "mlb" ? "MLB" : sport === "soccer_intl" ? "International soccer" : sport.replace(/_/g, " ");
}

function number(value: number | undefined): string {
  return value === undefined ? "not published" : value.toLocaleString("en-US");
}

function metricValue(sport: StateReliabilitySport, timeBucket: string, probabilityBucket: string, source: StateReliabilitySource, metric: StateReliabilityMetric): string {
  const row = stateReliabilityRow(sport, timeBucket, probabilityBucket, source);
  if (!row) return "not published";
  const value = stateReliabilityMetricValue(row, metric);
  return metric === "support" ? number(value) : `${value.toFixed(2)} pp`;
}

function cellTone(row: ReturnType<typeof stateReliabilityRow>, metric: StateReliabilityMetric, sport: StateReliabilitySport): string {
  if (!row) return "sr-cell-missing";
  if (metric === "signed-gap") {
    const gap = stateReliabilityMetricValue(row, metric);
    return gap === 0 ? "sr-cell-neutral" : gap > 0 ? "sr-cell-gap-positive" : "sr-cell-gap-negative";
  }
  if (metric !== "support") return "sr-cell-neutral";
  const largestSupport = Math.max(...sport.rows.map(item => item.n));
  if (row.n >= largestSupport * .67) return "sr-cell-support-high";
  if (row.n >= largestSupport * .34) return "sr-cell-support-mid";
  return "sr-cell-support-low";
}

function SourceGrid({ sport, source, metric }: { sport: StateReliabilitySport; source: StateReliabilitySource; metric: StateReliabilityMetric }) {
  const label = sources.find(item => item.id === source)?.label || source;
  return <section className="sr-grid-panel" aria-label={`${label} state grid`}>
    <h3>{label}</h3>
    <div className="sr-grid-wrap" role="region" aria-label={`${label} state grid, scrolls horizontally`} tabIndex={0} data-scroll-region>
      <table className="sr-grid-table">
        <caption>{label} by time and probability bucket for {sportLabel(sport.sport)}</caption>
        <thead><tr><th scope="col">Time</th>{sport.probabilityBuckets.map(bucket => <th scope="col" key={bucket}>{bucket}</th>)}</tr></thead>
        <tbody>{sport.timeBuckets.map(timeBucket => <tr key={timeBucket}><th scope="row">{timeBucket}</th>{sport.probabilityBuckets.map(probabilityBucket => {
          const row = stateReliabilityRow(sport, timeBucket, probabilityBucket, source);
          return <td key={probabilityBucket} className={cellTone(row, metric, sport)} data-testid={`${source}-${timeBucket}-${probabilityBucket}`}>
            <strong>{metricValue(sport, timeBucket, probabilityBucket, source, metric)}</strong>
            <span className="sr-cell-support">n {number(row?.n)}</span>
          </td>;
        })}</tr>)}</tbody>
      </table>
    </div>
  </section>;
}

export function StateReliability({ sports }: { sports: StateReliabilitySport[] }) {
  const [sportId, setSportId] = useState(sports[0]?.sport || "");
  const [metric, setMetric] = useState<StateReliabilityMetric>("signed-gap");
  const selected = sports.find(sport => sport.sport === sportId) || sports[0];

  if (!selected) return <p className="sr-empty">No published state-conditioned calibration rows are available in this snapshot.</p>;

  const metricLabel = metrics.find(item => item.id === metric)?.label || metric;
  return <section className="sr-shell" aria-label="State reliability inspector">
    <div className="sr-controls">
      <label>Sport<select aria-label="State reliability sport" value={selected.sport} onChange={event => setSportId(event.target.value)}>{sports.map(sport => <option key={sport.sport} value={sport.sport}>{sportLabel(sport.sport)}</option>)}</select></label>
      <div className="sr-toggle" aria-label="State reliability metric">{metrics.map(item => <button key={item.id} type="button" aria-pressed={metric === item.id} onClick={() => setMetric(item.id)}>{item.label}</button>)}</div>
    </div>
    <p className="sr-scope"><strong>{sportLabel(selected.sport)}</strong>: {number(selected.nForecastObservations)} forecast observations across {number(selected.nCells)} cells; {number(selected.nSkippedNoStateField)} skipped without a state field.</p>
    <p className="sr-pairing">Matching time and probability labels do not establish paired membership. Model and reference support are shown in aligned source grids; their populations can differ.</p>
    <p className="sr-metric" aria-live="polite">Showing <strong>{metricLabel}</strong> for {sportLabel(selected.sport)}. Signed gap is mean_y minus mean_p; absolute gap is the published calibration_error.</p>
    <div className="sr-legend" aria-label="Grid scales"><span className="sr-legend-gap">Signed gap scale: observed minus forecast</span><span className="sr-legend-support">Support scale: published observation count</span><span className="sr-legend-missing">not published</span></div>
    <div className="sr-grid-layout">{sources.map(source => <SourceGrid key={source.id} sport={selected} source={source.id} metric={metric} />)}</div>
    <div className="sr-table-wrap" role="region" aria-label={`${sportLabel(selected.sport)} state-conditioned rows`} tabIndex={0} data-scroll-region>
      <table className="sr-table"><caption>All published state-conditioned rows for {sportLabel(selected.sport)}</caption><thead><tr><th>Source</th><th>Time bucket</th><th>Probability bucket</th><th>n</th><th>Mean forecast</th><th>Observed frequency</th><th>Signed gap (pp)</th><th>Absolute gap (pp)</th></tr></thead><tbody>{selected.rows.map(row => <tr key={`${row.source}-${row.timeBucket}-${row.probabilityBucket}`}><td>{row.source === "market" ? "Reference" : "Model"}</td><td>{row.timeBucket}</td><td>{row.probabilityBucket}</td><td>{number(row.n)}</td><td>{(row.meanP * 100).toFixed(2)}%</td><td>{(row.meanY * 100).toFixed(2)}%</td><td>{stateReliabilityMetricValue(row, "signed-gap").toFixed(2)} pp</td><td>{stateReliabilityMetricValue(row, "absolute-gap").toFixed(2)} pp</td></tr>)}</tbody></table>
    </div>
    <p className="sr-source-fields">Source fields: state_conditioned_calibration.json -&gt; sports[sport].n_records, n_skipped_no_state_field, and buckets[] -&gt; time_bucket, prob_bucket, source, n, mean_p, mean_y, calibration_error.</p>
  </section>;
}

export default StateReliability;
