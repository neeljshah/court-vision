"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowLeft, ArrowUpRight, Download, Link2, RotateCcw, Search, X } from "lucide-react";
import type { ResearchAnalysis } from "@/lib/analytics/researchTypes";
import { displayMeasurement as display, rankedRows, type LabRow } from "@/lib/analytics/labTypes";
import { sourceUrl } from "@/lib/analytics/dashboardTypes";
import { DistributionSummary, DistributionPlot } from "@/components/analytics/lab/DistributionSummary";
import { RankedPlot, ScatterPlot } from "@/components/analytics/lab/LabPlot";
import { useResearchView } from "./useResearchView";
import { LabTable, exportLabCSV } from "@/components/analytics/lab/LabTable";
import { ResearchProvenance } from "./ResearchProvenance";
import { MeasurementPosition } from "../lab/MeasurementPosition";
import { ResearchSourceContext } from "./ResearchSourceContext";
import { MeasurementCoverage } from "./MeasurementCoverage";
import { matchesResearchPopulation, researchComparisonPolicy } from "@/lib/analytics/researchComparisonPolicy";

export default function ResearchDetail({ analysis: a, related }: { analysis: ResearchAnalysis; related: { id: string; title: string }[] }) {
  const { state, change, reset } = useResearchView(a);
  const { metric, second, group, query, ascending, view } = state;
  const [copyStatus, setCopyStatus] = useState("");
  const inspector = useRef<HTMLElement>(null), trigger = useRef<Element | null>(null);
  const field = a.fields.find(f => f.key === metric) || a.fields[0], y = a.fields.find(f => f.key === second) || a.fields[1] || field;
  const comparison = researchComparisonPolicy(a.rows, a);
  const activePopulation = comparison.populations.find(item => item.key === state.population) || comparison.populations.find(item => item.compatibility === "compatible");
  const showAllRows = !comparison.compatible && state.population === "all";
  const selectedCompatibility = showAllRows ? "unknown" : activePopulation?.compatibility || (comparison.compatible ? "compatible" : "unknown");
  const suppressPooledSummaries = selectedCompatibility !== "compatible";
  const groups = Array.from(new Set(a.rows.map(r => r.group)));
  const terms = query.toLowerCase().trim().split(/\s+/).filter(Boolean);
  const publishedPopulation = comparison.compatible ? a.rows.filter(r => group === "all" || r.group === group) : showAllRows ? a.rows : activePopulation ? a.rows.filter(r => matchesResearchPopulation(r, activePopulation)) : [];
  const aggregateIds = new Set(comparison.aggregateRows.map(row => row.id));
  const aggregateRows = publishedPopulation.filter(row => aggregateIds.has(row.id));
  const population = publishedPopulation.filter(row => !aggregateIds.has(row.id));
  const filtered = population.filter(r => terms.every(t => `${r.label} ${r.group} ${r.note || ""}`.toLowerCase().includes(t)));
  const ranked = rankedRows(filtered, metric, ascending);
  // A population that may not be pooled keeps published source order; only a compatible one is ranked.
  const rows = suppressPooledSummaries ? filtered : [...ranked, ...filtered.filter(r => r.values[metric] === null || !Number.isFinite(r.values[metric]))];
  const selected = publishedPopulation.find(r => r.id === state.row && terms.every(t => `${r.label} ${r.group} ${r.note || ""}`.toLowerCase().includes(t)));
  const inspect = (r: LabRow) => { trigger.current = document.activeElement; change({ row: r.id }); };
  const close = () => { change({ row: "" }); if (trigger.current instanceof HTMLElement || trigger.current instanceof SVGElement) trigger.current.focus(); };
  useEffect(() => { if (selected) inspector.current?.focus(); }, [selected]);
  useEffect(() => setCopyStatus(""), [state]);
  const copyView = async () => {
    try { await navigator.clipboard.writeText(window.location.href); setCopyStatus("View link copied."); }
    catch { setCopyStatus("Copy the page address from your browser; it preserves this view."); }
  };
  return <div className="cv-workspace research-page"><div className="cv-workspace-inner">
    <Link className="research-back" href={`/analytics/browse/?sport=${a.sport}&kind=derived`}><ArrowLeft size={15} /> Analytics library</Link>
    <header className="research-heading"><p className="cv-eyebrow">{a.sport === "all" ? "Cross-sport" : a.sport.toUpperCase()} / {a.category}</p><h1>{a.title}</h1><p>{a.description}</p><div className="research-tags"><span>{a.novelty}</span><span>{a.rows.length} published rows</span><span>{a.fields.length} fields</span><span>{a.sources?.length ? "Source dates and observation windows below" : a.asOf ? `Source as of ${a.asOf.slice(0, 10)}` : "Date varies or is unrecorded; see scope"}</span></div></header>
    <div className="research-layout"><section className="cv-panel research-measurements" aria-label="Interactive analysis">
      <ResearchSourceContext sources={a.sources} fields={a.fields} />
      <div className="research-panel-title"><div><p className="cv-eyebrow">Published measurements</p><h2>Choose a measurement</h2></div><button className="lab-export" disabled={!rows.length} onClick={() => exportLabCSV(a, rows)}><Download size={14} /> Export CSV</button></div>
      <div className="lab-controls"><label className="lab-field-label lab-primary-field">Measurement<select value={metric} onChange={e => change({ metric: e.target.value })}>{a.fields.map(f => <option key={f.key} value={f.key}>{f.label}</option>)}</select></label><label className="lab-field-label">Population<select value={comparison.compatible ? group : showAllRows ? "all" : activePopulation?.key || ""} onChange={e => comparison.compatible ? change({ group: e.target.value, row: "" }) : change({ population: e.target.value, row: "" })}>{comparison.compatible ? <><option value="all">All published groups</option>{groups.map(g => <option key={g}>{g}</option>)}</> : <><option value="all">Show all rows (not comparable)</option>{comparison.populations.map(item => <option key={item.key} value={item.key}>{item.label}</option>)}</>}</select></label><label className="lab-field-label">Order<select value={ascending ? "asc" : "desc"} onChange={e => change({ ascending: e.target.value === "asc" })}><option value="desc">Highest first</option><option value="asc">Lowest first</option></select></label></div>
      {!comparison.compatible && <section className="lab-cohort-notice" aria-label="Population comparison notice"><p>{comparison.reason} {showAllRows ? "All rows are shown without a pooled ranking, median, or percentile." : selectedCompatibility === "unknown" ? "The selected population has no complete published definition, so rankings and summaries are unavailable." : `Showing ${activePopulation?.label || "one population"} by default.`}</p></section>}
      <div className="research-chart-toolbar"><div className="cv-segment">{[["rank", "Ranked bars"], ["scatter", "Scatter plot"], ["table", "Data table"], ["distribution", "Distribution"]].map(([id, label]) => <button key={id} aria-pressed={view === id} onClick={() => change({ view: id })}>{label}</button>)}</div><label className="research-search"><Search size={14} /><span className="sr-only">Search analysis rows</span><input value={query} placeholder={a.id.includes("matchup") ? "Find a team or pairing" : "Find a row"} onChange={e => change({ query: e.target.value, row: "" })} /></label></div>
      <p className="cv-muted" role="status">{filtered.length} matching {filtered.length === 1 ? "row" : "rows"}; {ranked.length} {ranked.length === 1 ? "contains" : "contain"} {field.label.toLowerCase()}.</p>
      <div className="research-view-actions"><button className="lab-export" onClick={copyView}><Link2 size={14} /> Copy view link</button><button className="lab-export" onClick={reset}><RotateCcw size={14} /> Reset view</button><span aria-live="polite">{copyStatus}</span></div>
      <p className="cv-footnote">CSV includes {rows.length} matching {rows.length === 1 ? "row" : "rows"}, all fields, and source context; missing values stay blank.</p>
      {view === "scatter" && <label className="lab-field-label lab-second-axis">Vertical measurement<select value={second} onChange={e => change({ second: e.target.value })}>{a.fields.map(f => <option key={f.key} value={f.key}>{f.label}</option>)}</select></label>}
      {!suppressPooledSummaries && view !== "scatter" && <DistributionSummary rows={filtered} field={field} />}
      {!suppressPooledSummaries && <MeasurementCoverage rows={population} fields={a.fields} selectedKey={metric} populationLabel={comparison.compatible ? group === "all" ? "All published groups" : group : activePopulation?.label || "Selected population"} onSelect={key => change({ metric: key })} />}
      {selected && <section ref={inspector} tabIndex={-1} className="lab-inspector" aria-label="Selected measurement" onKeyDown={e => { if (e.key === "Escape") close(); }}><button aria-label="Close measurement" className="lab-close" onClick={close}><X size={17} /></button><p className="cv-eyebrow">{selected.group}</p><h3>{selected.label}</h3><dl>{a.fields.map(f => <div key={f.key}><dt>{f.label}</dt><dd>{display(selected.values[f.key], f)}</dd></div>)}</dl>{selected.note && <p>{selected.note}</p>}{selected.href && <Link className="research-entity-link" href={selected.href} prefetch={false}>Open entity card <ArrowUpRight size={14} /></Link>}{!suppressPooledSummaries && !aggregateIds.has(selected.id) && <MeasurementPosition rows={population} field={field} selected={selected} populationLabel={comparison.compatible ? group === "all" ? "All published groups" : group : activePopulation?.label || "Selected population"} />}<ResearchProvenance analysis={a} row={selected} fields={a.fields} resultField={field} /></section>}
      {!filtered.length ? <div className="cv-empty">No published rows match this search and population.</div> : suppressPooledSummaries && view !== "table" ? <div className="cv-empty">Rankings, distributions, and relative positions require a complete published population. The data table remains available.</div> : view === "table" ? <LabTable key={`${state.population}-${group}-${query}`} dataset={a} rows={rows} onSelect={inspect} /> : view === "distribution" ? <DistributionPlot rows={filtered} field={field} /> : view === "scatter" ? <ScatterPlot rows={filtered} x={field} y={y} onSelect={inspect} /> : ranked.length ? <RankedPlot rows={ranked} field={field} onSelect={inspect} /> : <div className="cv-empty">This measurement is unavailable for the selected population. The data table preserves missing values.</div>}
      {aggregateRows.length > 0 && <section className="research-whole-corpus" aria-label="Whole-corpus estimates"><div><p className="cv-eyebrow">Published aggregate</p><h3>Whole-corpus estimates</h3><p className="cv-footnote">These estimates cover the full published sport corpus. They are shown separately from game phases and are not ranked with them.</p></div><LabTable key={`aggregate-${state.population}`} dataset={a} rows={aggregateRows} onSelect={inspect} /></section>}
    </section><aside className="research-method"><section><p className="cv-eyebrow">01 / Interpretation</p><h2>What this measures</h2><p>{a.interpretation}</p></section><section><p className="cv-eyebrow">02 / Calculation</p><code>{a.formula}</code><p>Use the table to inspect available fields and the source JSON to trace the formula inputs. CSV percentage values are stored as fractions.</p></section><section><p className="cv-eyebrow">03 / Population & limits</p><p>{a.scope}</p><p className="research-caveat">{a.caveat}</p></section><section><p className="cv-eyebrow">04 / Source & method references</p><a href={sourceUrl(a.source)} target="_blank" rel="noreferrer">Published source JSON <ArrowUpRight size={14} /></a>{a.references.map(r => <a key={r.url} href={r.url} target="_blank" rel="noreferrer">{r.title} <ArrowUpRight size={14} /></a>)}<p>References explain ingredients and prior methods. They do not validate this derived analysis or establish its originality.</p></section></aside></div>
    {related.length > 0 && <section className="research-related"><p className="cv-eyebrow">Related analyses</p><div>{related.map(r => <Link href={`/analytics/research/${r.id}/`} key={r.id}>{r.title}<ArrowUpRight size={19} /></Link>)}</div></section>}
  </div></div>;
}
