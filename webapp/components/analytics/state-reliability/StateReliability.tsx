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
  return value === undefined ? "Not published" : value.toLocaleString("en-US");
}

function metricValue(sport: StateReliabilitySport, timeBucket: string, probabilityBucket: string, source: StateReliabilitySource, metric: StateReliabilityMetric): string {
  const row = stateReliabilityRow(sport, timeBucket, probabilityBucket, source);
  if (!row) return "Not published";
  const value = stateReliabilityMetricValue(row, metric);
  return metric === "support" ? number(value) : `${value.toFixed(2)} pp`;
}

function SourceGrid({ sport, source, metric }: { sport: StateReliabilitySport; source: StateReliabilitySource; metric: StateReliabilityMetric }) {
  const label = sources.find(item => item.id === source)?.label || source;
  return <section className="sr-grid-panel" aria-label={`${label} state grid`}>
    <h3>{label}</h3>
    <div className="sr-grid-wrap" data-scroll-region>
      <table className="sr-grid-table">
        <caption>{label} by time and probability bucket for {sportLabel(sport.sport)}</caption>
        <thead><tr><th scope="col">Time</th>{sport.probabilityBuckets.map(bucket => <th scope="col" key={bucket}>{bucket}</th>)}</tr></thead>
        <tbody>{sport.timeBuckets.map(timeBucket => <tr key={timeBucket}><th scope="row">{timeBucket}</th>{sport.probabilityBuckets.map(probabilityBucket => {
          const model = stateReliabilityRow(sport, timeBucket, probabilityBucket, "model");
          const reference = stateReliabilityRow(sport, timeBucket, probabilityBucket, "market");
          return <td key={probabilityBucket} data-testid={`${source}-${timeBucket}-${probabilityBucket}`}>
            <strong>{metricValue(sport, timeBucket, probabilityBucket, source, metric)}</strong>
            <span>Model n {number(model?.n)} | Reference n {number(reference?.n)}</span>
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
    <p className="sr-scope"><strong>{sportLabel(selected.sport)}</strong> has {number(selected.rows.length)} published state-conditioned rows. {number(selected.nSkippedNoStateField)} rows were skipped because the published state field was absent.</p>
    <p className="sr-pairing">Matching time and probability labels do not establish paired membership. Model and reference support are shown side by side in every cell; their populations can differ.</p>
    <p className="sr-metric" aria-live="polite">Showing <strong>{metricLabel}</strong> for {sportLabel(selected.sport)}. Signed gap is mean_y minus mean_p; absolute gap is the published calibration_error.</p>
    <div className="sr-grid-layout">{sources.map(source => <SourceGrid key={source.id} sport={selected} source={source.id} metric={metric} />)}</div>
    <div className="sr-table-wrap" role="region" aria-label={`${sportLabel(selected.sport)} state-conditioned rows`} data-scroll-region>
      <table className="sr-table"><caption>All published state-conditioned rows for {sportLabel(selected.sport)}</caption><thead><tr><th>Source</th><th>Time bucket</th><th>Probability bucket</th><th>n</th><th>Mean forecast</th><th>Observed frequency</th><th>Signed gap (pp)</th><th>Absolute gap (pp)</th></tr></thead><tbody>{selected.rows.map(row => <tr key={`${row.source}-${row.timeBucket}-${row.probabilityBucket}`}><td>{row.source === "market" ? "Reference" : "Model"}</td><td>{row.timeBucket}</td><td>{row.probabilityBucket}</td><td>{number(row.n)}</td><td>{(row.meanP * 100).toFixed(2)}%</td><td>{(row.meanY * 100).toFixed(2)}%</td><td>{stateReliabilityMetricValue(row, "signed-gap").toFixed(2)} pp</td><td>{stateReliabilityMetricValue(row, "absolute-gap").toFixed(2)} pp</td></tr>)}</tbody></table>
    </div>
    <p className="sr-source-fields">Source fields: state_conditioned_calibration.json -&gt; sports[sport].buckets[] -&gt; time_bucket, prob_bucket, source, n, mean_p, mean_y, calibration_error; and n_skipped_no_state_field.</p>
  </section>;
}

export default StateReliability;
