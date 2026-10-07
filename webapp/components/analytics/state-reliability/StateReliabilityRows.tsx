"use client";

import { useState } from "react";
import { stateReliabilityMetricValue, type StateReliabilityRow, type StateReliabilitySport } from "@/lib/analytics/stateReliability";
import { exportStateReliabilityCSV } from "@/lib/analytics/stateReliabilityCsv";

const orders = [
  { value: "published", label: "Published order" },
  { value: "gap-desc", label: "Largest absolute gap" },
  { value: "gap-asc", label: "Smallest absolute gap" },
  { value: "support-desc", label: "Most observations" },
  { value: "support-asc", label: "Fewest observations" },
] as const;
type Order = typeof orders[number]["value"];

export function StateReliabilityRows({ sport, label }: { sport: StateReliabilitySport; label: string }) {
  const [source, setSource] = useState("all");
  const [phase, setPhase] = useState("all");
  const [minimum, setMinimum] = useState(0);
  const [order, setOrder] = useState<Order>("published");
  const filtered = source !== "all" || phase !== "all" || minimum > 0;
  const rows = sport.rows.filter(row => (source === "all" || row.source === source)
    && (phase === "all" || row.timeBucket === phase) && row.n >= minimum);
  const sortMetric = order.startsWith("gap") ? "absolute-gap" : "support";
  if (order !== "published") rows.sort((a, b) => (order.endsWith("asc") ? 1 : -1)
    * (stateReliabilityMetricValue(a, sortMetric) - stateReliabilityMetricValue(b, sortMetric)));
  const direction = order.endsWith("asc") ? "ascending" : "descending";
  const gap = (row: StateReliabilityRow, metric: "signed-gap" | "absolute-gap") => `${stateReliabilityMetricValue(row, metric).toFixed(2)} pp`;

  function reset() {
    setSource("all"); setPhase("all"); setMinimum(0); setOrder("published");
  }

  return <section className="sr-row-inspector" aria-label="Published row explorer">
    <h2>Inspect published rows</h2>
    <p className="sr-pairing">Filter or sort the detail table. The grids above retain all published cells. Support counts forecast observations, not independent games; matching labels do not pair model and reference populations.</p>
    <div className="sr-controls">
      <label>Source<select aria-label="Row source" value={source} onChange={event => setSource(event.target.value)}>
        <option value="all">Both sources</option><option value="model">Model</option><option value="market">Reference</option>
      </select></label>
      <label>Time bucket<select aria-label="Row time bucket" value={phase} onChange={event => setPhase(event.target.value)}>
        <option value="all">All time buckets</option>{sport.timeBuckets.map(bucket => <option key={bucket}>{bucket}</option>)}
      </select></label>
      <label>Minimum support<select aria-label="Minimum row support" value={minimum} onChange={event => setMinimum(Number(event.target.value))}>
        {[0, 50, 100, 500, 1000].map(value => <option key={value} value={value}>{value === 0 ? "All published support" : `At least ${value.toLocaleString("en-US")} observations`}</option>)}
      </select></label>
      <label>Order<select aria-label="Row order" value={order} onChange={event => setOrder(event.target.value as Order)}>
        {orders.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}
      </select></label>
      <button className="sr-reset" type="button" onClick={reset} disabled={!filtered && order === "published"}>Reset table</button>
      <button className="sr-reset" type="button" onClick={() => exportStateReliabilityCSV(sport, rows)} disabled={!rows.length}>Download visible rows (CSV)</button>
    </div>
    <p className="sr-metric" role="status">Showing {rows.length} of {sport.rows.length} published rows for {label}.</p>
    <p className="sr-pairing">CSV keeps this row order, raw probabilities, percentage-point gaps, and source context. The artifact date is included; observation dates are not published. Missing cells are omitted, not exported as zero.</p>
    {rows.length ? <div className="sr-table-wrap" role="region" aria-label={`${label} state-conditioned rows`} tabIndex={0} data-scroll-region>
      <table className="sr-table">
        <caption>{filtered ? "Filtered published" : "All published"} state-conditioned rows for {label}</caption>
        <thead><tr><th scope="col">Source</th><th scope="col">Time bucket</th><th scope="col">Probability bucket</th>
          <th scope="col" aria-sort={order.startsWith("support") ? direction : undefined}>n</th>
          <th scope="col">Mean forecast</th><th scope="col">Observed frequency</th><th scope="col">Signed gap (pp)</th>
          <th scope="col" aria-sort={order.startsWith("gap") ? direction : undefined}>Absolute gap (pp)</th>
        </tr></thead>
        <tbody>{rows.map(row => <tr key={`${row.source}-${row.timeBucket}-${row.probabilityBucket}`}>
          <td>{row.source === "market" ? "Reference" : "Model"}</td><td>{row.timeBucket}</td><td>{row.probabilityBucket}</td>
          <td>{row.n.toLocaleString("en-US")}</td><td>{(row.meanP * 100).toFixed(2)}%</td><td>{(row.meanY * 100).toFixed(2)}%</td>
          <td>{gap(row, "signed-gap")}</td><td>{gap(row, "absolute-gap")}</td>
        </tr>)}</tbody>
      </table>
    </div> : <p className="sr-empty">No published rows match these filters. Lower the minimum support or reset the table.</p>}
  </section>;
}
