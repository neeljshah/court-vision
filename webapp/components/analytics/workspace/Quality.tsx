"use client";
import { useState } from "react";
import Link from "next/link";
import type { DashboardData, Sport } from "@/lib/analytics/dashboardTypes";
import { number, humanize } from "@/lib/analytics/dashboardTypes";
import { Empty, Panel } from "./Primitives";

export function Quality({ data, sport }: { data: DashboardData; sport: Sport }) {
  const [metric, setMetric] = useState<"brier" | "ece">("brier");
  const markets = data.markets.filter(m => sport === "all" || m.sport === sport);
  const history = data.history.filter(m => sport === "all" || m.sport === sport);
  return <div className="cv-quality"><Panel title="Model vs. market" eyebrow="Probability quality" source="calibration_by_market_type">
    <div className="cv-chart-toolbar"><div className="cv-segment" role="group" aria-label="Quality metric">{(["brier", "ece"] as const).map(m => <button key={m} aria-pressed={metric === m} onClick={() => setMetric(m)}>{m.toUpperCase()}</button>)}</div><span className="cv-muted">Lower is better</span></div>
    <div className="cv-legend"><span><i className="cv-dot cv-model" />CourtVision model</span><span><i className="cv-dot cv-market" />Market baseline</span></div>
    {markets.length === 0 && <Empty>No market-type scores published for this sport in this snapshot. Explore its research and entity profiles below.</Empty>}
    {markets.map(m => <div className="cv-comparison" key={m.id}><div className="cv-chart-label"><strong>{m.sport === "mlb" ? "Baseball" : "Soccer"} <span>{m.id === "mlb_total" ? "Totals" : "Game winner"}</span></strong><span>{number(m.n_rows)} rows</span></div>{m.scored ? <>
      {(["model", "market"] as const).map(kind => { const value = m[`${kind}_${metric}`]; return <div className="cv-bar-row" key={kind}><span>{kind === "model" ? "Model" : "Market"}</span><div className="cv-track"><div className={`cv-bar cv-${kind}`} style={{ width: `${Math.min(100, (value ?? 0) / .5 * 100)}%` }} /></div><b>{value === undefined ? "Unavailable" : value.toFixed(4)}</b></div>; })}
      <p className="cv-chart-context">{m.description}. Shared axis 0-0.50.</p>
    </> : <div className="cv-unscored"><b>Not scored</b><span>{m.reason}</span></div>}</div>)}
    <p className="cv-footnote">{metric === "brier" ? "Brier measures squared probability error, including calibration and resolution." : "ECE measures the weighted gap between forecast probability and observed frequency across 10 bins."} Rows can include multiple observations of a game; they are not independent games. These comparisons do not establish betting returns.</p>
    <Link href="/analytics/calibration" className="cv-text-button">Inspect every reliability bin</Link>
  </Panel><Panel title="How quality changes over time" eyebrow="Monthly snapshots" source="calibration_over_time">
    <p className="cv-muted">Same metric, separate sport cohorts. Only the two published months are shown.</p>
    {history.length === 0 ? <Empty>No monthly quality series published for this sport.</Empty> : <div className="cv-history-grid">{(["mlb", "soccer"] as const).filter(s => sport === "all" || sport === s).map(s => {
      const points = history.filter(p => p.sport === s).sort((a, b) => a.month.localeCompare(b.month));
      return <div key={s} className="cv-trend"><h3>{s === "mlb" ? "Baseball" : "Soccer"}</h3><svg viewBox="0 0 300 170" role="img" aria-label={`${s} ${metric.toUpperCase()} monthly model and market comparison; exact values in table below`}>
        {[0, .25, .5].map(v => <g key={v}><line x1="34" x2="278" y1={140 - v * 240} y2={140 - v * 240} stroke="var(--cv-line)" strokeDasharray="3 4" /><text x="0" y={144 - v * 240}>{v.toFixed(2)}</text></g>)}
        {(["model", "market"] as const).map(kind => <g key={kind} className={`cv-line-${kind}`}><polyline fill="none" strokeWidth="2.5" points={points.map((p, i) => `${55 + i * 190},${140 - p[`${kind}_${metric}`] * 240}`).join(" ")} />{points.map((p, i) => <circle key={p.month} cx={55 + i * 190} cy={140 - p[`${kind}_${metric}`] * 240} r="4"><title>{`${p.month}: ${p[`${kind}_${metric}`].toFixed(4)}`}</title></circle>)}</g>)}
        {points.map((p, i) => <text key={p.month} x={55 + i * 190} y="164" textAnchor="middle">{p.month}</text>)}
      </svg><table className="cv-mini-table"><caption className="sr-only">{humanize(s)} monthly {metric} measurements</caption><thead><tr><th>Month</th><th>Model</th><th>Market</th><th>Rows</th></tr></thead><tbody>{points.map(p => <tr key={p.month}><td>{p.month}</td><td>{p[`model_${metric}`].toFixed(4)}</td><td>{p[`market_${metric}`].toFixed(4)}</td><td>{number(p.n)}</td></tr>)}</tbody></table></div>;
    })}</div>}
    <p className="cv-footnote">June-July 2026. Changes in cohort composition can change these scores. Connecting observations is a visual guide, not an interpolated estimate.</p>
  </Panel></div>;
}
