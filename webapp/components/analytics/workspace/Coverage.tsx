"use client";
import { useState } from "react";
import Link from "next/link";
import { humanize, number, type DashboardData, type Sport } from "@/lib/analytics/dashboardTypes";
import { Empty, Panel } from "./Primitives";
const pitchNames: Record<string, string> = { FF: "Four-seam fastball", SI: "Sinker", SL: "Slider", CH: "Changeup", ST: "Sweeper", FC: "Cutter", CU: "Curveball", FS: "Splitter", KC: "Knuckle curve" };
export function Coverage({ data, sport }: { data: DashboardData; sport: Sport }) {
  const [pitch, setPitch] = useState("FF");
  const velocity = data.pitches.velocity.find(v => v.pitch_type === pitch);
  const distribution = data.pitches.distribution.find(v => v.pitch_type === pitch);
  const largestHistogramBin = Math.max(...data.coverage.histogram.map(bin => bin.dossiers));
  return <div className="cv-coverage-grid">{(sport === "all" || sport === "mlb") && <Panel title="Inside the pitch corpus" eyebrow="Baseball / 2025 Statcast" source="statcast_showcase">
    <div className="cv-big-number">{number(data.pitches.n)}<span>pitches in the published pull</span></div>
    <div className="cv-distribution">{data.pitches.distribution.slice(0, 9).map(p => <button key={p.pitch_type} aria-pressed={pitch === p.pitch_type} onClick={() => setPitch(p.pitch_type)} aria-label={`Inspect ${pitchNames[p.pitch_type] || p.pitch_type}`}><span>{p.pitch_type}</span><div className="cv-track"><i className="cv-bar cv-model" style={{ width: `${p.pct / 35 * 100}%` }} /></div><b>{p.pct.toFixed(1)}%</b></button>)}</div>
    <div className="cv-pitch-detail" aria-live="polite"><h3>{pitchNames[pitch] || pitch}</h3><p>{distribution ? number(distribution.n) : "Unavailable"} pitches in mix</p>{velocity ? <><div className="cv-velocity">{(["p10", "p50", "p90"] as const).map(k => <div key={k}><span>{k === "p50" ? "Median" : k.toUpperCase()}</span><strong>{velocity[k].toFixed(1)}<small> mph</small></strong></div>)}</div><p className="cv-footnote">Velocity observations: {number(velocity.n)}. Counts differ when velocity is missing.</p></> : <p>Velocity percentiles unavailable.</p>}</div>
    <p className="cv-footnote">Nine most common pitch types shown. Descriptive pitch mix and velocity; not a predictive result.</p>
  </Panel>}{(sport === "all" || sport === "nba") && <Panel title="How complete are player dossiers?" eyebrow="Basketball / coverage audit" source="dossier_completeness">
    <div className="cv-coverage-stats"><div className="cv-big-number">{data.coverage.medianCategories} of {data.coverage.categoriesTotal}<span>median categories filled: {data.coverage.medianCategories} of {data.coverage.categoriesTotal} ({(data.coverage.medianCategoriesShare * 100).toFixed(1)}%)</span></div><div className="cv-big-number">{(data.coverage.publishedCompletenessScore * 100).toFixed(1)}%<span>published completeness score: {(data.coverage.publishedCompletenessScore * 100).toFixed(1)}%</span></div><div className="cv-big-number">{number(data.coverage.n)}<span>dossiers audited</span></div></div>
    <p className="cv-footnote">The artifact does not define how the published completeness score is derived.</p>
    <h3>Categories filled per dossier</h3><div className="cv-fill-rates" role="img" aria-label="Categories filled histogram">{data.coverage.histogram.map(bin => <div key={bin.categoriesFilled}><div><span>{bin.categoriesFilled} categories</span><b>{number(bin.dossiers)} dossiers ({(bin.share * 100).toFixed(1)}%)</b></div><div className="cv-track"><i className="cv-bar cv-model" style={{ width: `${bin.dossiers / largestHistogramBin * 100}%` }} /></div></div>)}</div>
    <h3>Category fill rates</h3><div className="cv-fill-rates">{data.coverage.rates.map(r => <div key={r.name}><div><span>{humanize(r.name)}</span><b>{(r.value * 100).toFixed(1)}%</b></div><div className="cv-track"><i className="cv-bar cv-market" style={{ width: `${r.value * 100}%` }} /></div></div>)}</div><p className="cv-footnote">Fill rate is the fraction of dossiers containing a category. Presence does not establish accuracy.</p>
  </Panel>}{sport !== "all" && sport !== "nba" && sport !== "mlb" && <Panel title="Coverage for this sport"><Empty>No equivalent pitch or dossier audit is published for this sport. <Link href="/analytics/compare/">Open entity profiles.</Link></Empty></Panel>}</div>;
}
