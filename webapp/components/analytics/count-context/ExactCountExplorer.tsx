"use client";

import Link from "next/link";
import { useMemo, useState, type ReactNode } from "react";
import type { ExactCountData } from "@/lib/analytics/exactCountContext";
import styles from "./ExactCountExplorer.module.css";

type Metric = "inZoneRate" | "strikeRate" | "topPitchPct";

const metrics: Array<{ key: Metric; label: string }> = [
  { key: "inZoneRate", label: "In-zone rate" },
  { key: "strikeRate", label: "Coded strike rate" },
  { key: "topPitchPct", label: "Top pitch share" },
];
const formatCount = (value: number | null): string => value === null ? "Not published" : value.toLocaleString("en-US");
const formatRate = (value: number | null, metric: Metric): string => {
  if (value === null) return "Not published";
  const percent = metric === "topPitchPct" ? value : value * 100;
  return `${percent.toFixed(2)}%`;
};
const countId = (balls: number, strikes: number): string => `${balls}-${strikes}`;
const countClass = (value: string): string => {
  if (value === "ahead") return "Pitcher ahead";
  if (value === "behind") return "Pitcher behind";
  if (value === "even") return "Even";
  return value;
};

function DetailValue({ label, children }: { label: string; children: ReactNode }) {
  return <div><dt>{label}</dt><dd>{children}</dd></div>;
}

export function ExactCountExplorer({ data }: { data: ExactCountData }) {
  const [selectedId, setSelectedId] = useState("0-0");
  const [metric, setMetric] = useState<Metric>("inZoneRate");
  const [compareId, setCompareId] = useState("0-0");
  const rows = useMemo(() => new Map(data.rows.map(row => [row.id, row])), [data.rows]);
  const selected = rows.get(selectedId) || data.rows[0] || null;
  const effectiveCompareId = rows.has(compareId) ? compareId : data.rows[0]?.id || "";
  const compare = rows.get(effectiveCompareId) || null;
  const selectedMetric = selected?.[metric] ?? null;
  const compareMetric = compare?.[metric] ?? null;
  const difference = selectedMetric === null || compareMetric === null
    ? null : (metric === "topPitchPct" ? selectedMetric - compareMetric : (selectedMetric - compareMetric) * 100);

  if (!selected) return <section className={styles.empty} aria-label="Exact count explorer">No published exact-count rows are available in this snapshot.</section>;

  return <section className={styles.explorer} aria-label="Exact MLB count explorer">
    <header className={styles.header}>
      <div><p className="overline">Exact count view</p><h2>What changes before the next pitch?</h2></div>
      <p>Local 2025 Statcast pull. Snapshot {data.asOf ? <time dateTime={data.asOf}>{data.asOf.slice(0, 10)}</time> : "date not published"}. {data.rows.length} of 12 counts available.</p>
    </header>
    <p className={styles.intro}>Choose the balls-strikes count before a pitch. Each cell shows the selected published measurement; a count cohort is not a rate denominator.</p>

    <div className={styles.metricGroup} aria-label="Displayed metric">
      {metrics.map(item => <button key={item.key} type="button" aria-pressed={metric === item.key} onClick={() => setMetric(item.key)}>{item.label}</button>)}
    </div>

    <div className={styles.matrixWrap} role="region" aria-label="Balls strikes count matrix">
      <p className={styles.axis}>Strikes before pitch</p>
      <div className={styles.matrix}>
        <span className={styles.corner}>Balls<br />before pitch</span>
        {[0, 1, 2].map(strikes => <span className={styles.columnLabel} key={strikes}>{strikes} strikes</span>)}
        {[0, 1, 2, 3].flatMap(balls => [
          <span className={styles.rowLabel} key={`label-${balls}`}>{balls} balls</span>,
          ...[0, 1, 2].map(strikes => {
            const id = countId(balls, strikes);
            const row = rows.get(id);
            return <button className={styles.cell} key={id} type="button" disabled={!row} aria-pressed={selected.id === id}
              aria-label={`Use count ${id}, ${formatRate(row?.[metric] ?? null, metric)}`}
              onClick={() => setSelectedId(id)}><strong>{id}</strong><span>{formatRate(row?.[metric] ?? null, metric)}</span></button>;
          }),
        ])}
      </div>
    </div>

    <section className={styles.details} aria-live="polite" aria-label={`Count ${selected.id} details`}>
      <div><p className="overline">Selected count</p><h3>{selected.balls}-{selected.strikes} before pitch</h3><p>{countClass(selected.leverageClass)} count. Balls and strikes are the count before this pitch.</p></div>
      <dl>
        <DetailValue label="Pitch cohort n">{formatCount(selected.n)}</DetailValue>
        <DetailValue label="Top pitch">{selected.topPitchType || "Not published"}</DetailValue>
        <DetailValue label="Top pitch share">{formatRate(selected.topPitchPct, "topPitchPct")}</DetailValue>
        <DetailValue label="In-zone rate">{formatRate(selected.inZoneRate, "inZoneRate")}</DetailValue>
        <DetailValue label="Coded strike rate">{formatRate(selected.strikeRate, "strikeRate")}</DetailValue>
      </dl>
    </section>

    <section className={styles.compare} aria-label="Count comparison">
      <label htmlFor="exact-count-compare">Compare with</label>
      <select id="exact-count-compare" value={effectiveCompareId} onChange={event => setCompareId(event.target.value)}>
        {data.rows.map(row => <option key={row.id} value={row.id}>{row.id}</option>)}
      </select>
      <p>{selected.id}: <strong>{formatRate(selectedMetric, metric)}</strong>; {compare?.id || "Not published"}: <strong>{formatRate(compareMetric, metric)}</strong>; signed difference: <strong>{difference === null ? "Not published" : `${difference >= 0 ? "+" : ""}${difference.toFixed(2)} pp`}</strong>.</p>
      <small>Descriptive comparison only. It applies no weighting or statistical inference.{metric === "topPitchPct" ? " Top pitch share compares the most-used pitch in each count; it may differ in other snapshots." : ""}</small>
    </section>

    <p className={styles.denominator}>The source does not publish pitch-type, coded-strike, or in-zone rate denominators for exact counts. <strong>n is the count cohort size only; it is not used as a rate denominator.</strong> Coded strikes are Statcast <code>type S</code> (called, swinging, and foul strikes), not whiffs.</p>

    <details className={styles.tableDetails}><summary>Published count states ({data.rows.length} of 12 available)</summary><div className={styles.tableWrap}><table><caption>Published exact-count values</caption><thead><tr><th>Count</th><th>Class</th><th>n</th><th>Top pitch</th><th>Top share</th><th>In zone</th><th>Coded strikes</th></tr></thead><tbody>{data.rows.map(row => <tr key={row.id}><th scope="row">{row.id}</th><td>{countClass(row.leverageClass)}</td><td>{formatCount(row.n)}</td><td>{row.topPitchType || "Not published"}</td><td>{formatRate(row.topPitchPct, "topPitchPct")}</td><td>{formatRate(row.inZoneRate, "inZoneRate")}</td><td>{formatRate(row.strikeRate, "strikeRate")}</td></tr>)}</tbody></table></div></details>
    <footer className={styles.footer}>Source: <Link href="/analytics/m/mlb_count_leverage/">MLB count leverage</Link>. Statcast field definitions: <a href="https://baseballsavant.mlb.com/csv-docs">Baseball Savant CSV documentation</a>. Descriptive published snapshot; no full pitch mix or independent-game totals are inferred.</footer>
  </section>;
}
