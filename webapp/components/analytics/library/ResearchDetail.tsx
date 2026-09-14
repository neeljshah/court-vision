"use client";
import { useState } from "react";
import Link from "next/link";
import { ArrowLeft, ArrowUpRight, Download, Search, X } from "lucide-react";
import type { ResearchAnalysis } from "@/lib/analytics/researchTypes";
import { displayMeasurement as display, rankedRows, type LabRow } from "@/lib/analytics/labTypes";
import { sourceUrl } from "@/lib/analytics/dashboardTypes";
import { RankedPlot, ScatterPlot } from "@/components/analytics/lab/LabPlot";
import { LabTable, exportLabCSV } from "@/components/analytics/lab/LabTable";

export default function ResearchDetail({ analysis: a, related }: { analysis: ResearchAnalysis; related: { id: string; title: string }[] }) {
  const [metric, setMetric] = useState(a.fields[0].key), [second, setSecond] = useState(a.fields[1]?.key || a.fields[0].key);
  const [group, setGroup] = useState("all"), [query, setQuery] = useState(""), [ascending, setAscending] = useState(false);
  const [view, setView] = useState("rank"), [selected, setSelected] = useState<LabRow | null>(null);
  const field = a.fields.find(f => f.key === metric)!, y = a.fields.find(f => f.key === second)!;
  const groups = Array.from(new Set(a.rows.map(r => r.group)));
  const terms = query.toLowerCase().trim().split(/\s+/).filter(Boolean);
  const filtered = a.rows.filter(r => (group === "all" || r.group === group) && terms.every(t => `${r.label} ${r.group} ${r.note || ""}`.toLowerCase().includes(t)));
  const ranked = rankedRows(filtered, metric, ascending);
  const rows = view === "table" ? [...ranked, ...filtered.filter(r => r.values[metric] === null || !Number.isFinite(r.values[metric]))] : ranked;
  const filter = (change: () => void) => { change(); setSelected(null); };
  return <div className="cv-workspace research-page"><div className="cv-workspace-inner">
    <Link className="research-back" href={`/analytics/browse/?sport=${a.sport}&kind=derived`}><ArrowLeft size={15} /> Analytics library</Link>
    <header className="research-heading"><p className="cv-eyebrow">{a.sport === "all" ? "Cross-sport" : a.sport.toUpperCase()} / {a.category}</p><h1>{a.title}</h1><p>{a.description}</p><div className="research-tags"><span>{a.novelty}</span><span>{a.rows.length} published rows</span><span>{a.fields.length} fields</span><span>{a.asOf ? `Source as of ${a.asOf.slice(0, 10)}` : "Date varies or is unrecorded; see scope"}</span></div></header>
    <div className="research-layout"><section className="cv-panel research-measurements" aria-label="Interactive analysis">
      <div className="research-panel-title"><div><p className="cv-eyebrow">Explore the measurements</p><h2>Change the lens.</h2></div><button className="lab-export" onClick={() => exportLabCSV(a, rows)}><Download size={14} /> Export CSV</button></div>
      <div className="lab-controls"><label className="lab-field-label lab-primary-field">Measurement<select value={metric} onChange={e => setMetric(e.target.value)}>{a.fields.map(f => <option key={f.key} value={f.key}>{f.label}</option>)}</select></label><label className="lab-field-label">Population<select value={group} onChange={e => filter(() => setGroup(e.target.value))}><option value="all">All published groups</option>{groups.map(g => <option key={g}>{g}</option>)}</select></label><label className="lab-field-label">Order<select value={ascending ? "asc" : "desc"} onChange={e => setAscending(e.target.value === "asc")}><option value="desc">Highest first</option><option value="asc">Lowest first</option></select></label></div>
      <div className="research-chart-toolbar"><div className="cv-segment">{[["rank", "Ranked bars"], ["scatter", "Scatter plot"], ["table", "Data table"]].map(([id, label]) => <button key={id} aria-pressed={view === id} onClick={() => setView(id)}>{label}</button>)}</div><label className="research-search"><Search size={14} /><span className="sr-only">Search analysis rows</span><input value={query} placeholder={a.id.includes("matchup") ? "Find a team or pairing" : "Find a row"} onChange={e => filter(() => setQuery(e.target.value))} /></label></div>
      <p className="cv-muted" role="status">{filtered.length} matching rows; {ranked.length} contain {field.label.toLowerCase()}.</p>
      {view === "scatter" && <label className="lab-field-label lab-second-axis">Vertical measurement<select value={second} onChange={e => setSecond(e.target.value)}>{a.fields.map(f => <option key={f.key} value={f.key}>{f.label}</option>)}</select></label>}
      {!filtered.length ? <div className="cv-empty">No published rows match this search and population.</div> : view === "table" ? <LabTable key={`${group}-${query}`} dataset={a} rows={rows} onSelect={setSelected} /> : view === "scatter" ? <ScatterPlot rows={filtered} x={field} y={y} onSelect={setSelected} /> : ranked.length ? <RankedPlot rows={ranked} field={field} onSelect={setSelected} /> : <div className="cv-empty">This measurement is unavailable for the selected population. The data table preserves missing values.</div>}
      {selected && <section className="lab-inspector" aria-label="Selected measurement"><button aria-label="Close measurement" className="lab-close" onClick={() => setSelected(null)}><X size={17} /></button><p className="cv-eyebrow">{selected.group}</p><h3>{selected.label}</h3><dl>{a.fields.map(f => <div key={f.key}><dt>{f.label}</dt><dd>{display(selected.values[f.key], f)}</dd></div>)}</dl>{selected.note && <p>{selected.note}</p>}</section>}
    </section><aside className="research-method"><section><p className="cv-eyebrow">01 / How to read it</p><h2>The question behind the number.</h2><p>{a.interpretation}</p></section><section><p className="cv-eyebrow">02 / Calculation</p><code>{a.formula}</code><p>Use the table to inspect available fields and the source JSON to trace the formula inputs. CSV percentage values are stored as fractions.</p></section><section><p className="cv-eyebrow">03 / Population & limits</p><p>{a.scope}</p><p className="research-caveat">{a.caveat}</p></section><section><p className="cv-eyebrow">04 / Source & method references</p><a href={sourceUrl(a.source)} target="_blank" rel="noreferrer">Published source JSON <ArrowUpRight size={14} /></a>{a.references.map(r => <a key={r.url} href={r.url} target="_blank" rel="noreferrer">{r.title} <ArrowUpRight size={14} /></a>)}<p>References explain ingredients and prior methods. They do not validate this derived analysis or establish its originality.</p></section></aside></div>
    {related.length > 0 && <section className="research-related"><p className="cv-eyebrow">Keep investigating</p><div>{related.map(r => <Link href={`/analytics/research/${r.id}/`} key={r.id}>{r.title}<ArrowUpRight size={19} /></Link>)}</div></section>}
  </div></div>;
}
