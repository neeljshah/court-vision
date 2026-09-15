"use client";
import { useEffect, useRef, useState } from "react";
import { ArrowUpRight, Download, Search, SlidersHorizontal, X } from "lucide-react";
import { base, humanize, moduleUrl, sourceUrl, SPORTS, type Sport } from "@/lib/analytics/dashboardTypes";
import { displayMeasurement as display, rankedRows, type LabData, type LabRow } from "@/lib/analytics/labTypes";
import { DistributionSummary, DistributionPlot } from "./DistributionSummary";
import { RankedPlot, ScatterPlot } from "./LabPlot";
import { LabTable, exportLabCSV } from "./LabTable";
import { Empty } from "@/components/analytics/workspace/Primitives";
import { labViewSearch, readLabViewState, type LabViewState } from "./labViewState";

const sportGroup = (sport: Sport) => sport === "soccer" ? "INTERNATIONAL SOCCER" : sport.toUpperCase();
const rowLabel = (count: number) => `${count} published ${count === 1 ? "row" : "rows"}`;
const countVerb = (count: number, singular: string, plural: string) => count === 1 ? singular : plural;
const rowsForSport = (dataset: LabData["datasets"][number], sport: Sport) =>
  dataset.sport === "all" && sport !== "all" ? dataset.rows.filter(r => r.group === sportGroup(sport)) : dataset.rows;

export default function MeasurementLab({ data }: { data: LabData }) {
  const [viewState, setViewState] = useState<LabViewState>(() => readLabViewState("", data));
  const [restored, setRestored] = useState(false);
  const inspector = useRef<HTMLElement>(null), trigger = useRef<Element | null>(null);
  const { id, sport, fieldKey, otherKey, mode, query, group, ascending, selectedId } = viewState;
  const update = (change: Partial<LabViewState>) => setViewState(current => ({ ...current, ...change }));
  const dataset = data.datasets.find(d => d.id === id) || data.datasets[0];
  const field = dataset.fields.find(f => f.key === fieldKey) || dataset.fields[0];
  const other = dataset.fields.find(f => f.key === otherKey) || dataset.fields[1] || field;
  const sportRows = rowsForSport(dataset, sport);
  const groups = Array.from(new Set(sportRows.map(r => r.group)));
  const filtered = sportRows.filter(r => (group === "all" || r.group === group) && `${r.label} ${r.group} ${r.note || ""}`.toLowerCase().includes(query.toLowerCase()));
  const ranked = rankedRows(filtered, field.key, ascending);
  const choices = data.datasets.filter(d => sport === "all" || d.sport === sport || d.sport === "all");
  const categories = Array.from(new Set(choices.map(d => d.category)));
  const sportLabel = SPORTS.find(s => s.id === sport)?.label || sport;
  const choose = (value: string) => {
    const next = data.datasets.find(d => d.id === value) || data.datasets[0];
    update({ id: next.id, fieldKey: next.fields[0].key, otherKey: next.fields[1]?.key || next.fields[0].key, query: "", group: "all", selectedId: null });
  };
  const chooseSport = (nextSport: Sport) => {
    const compatible = data.datasets.find(d => nextSport === "all" || d.sport === nextSport || d.sport === "all");
    const next = compatible && (dataset.sport !== nextSport && dataset.sport !== "all") ? compatible : dataset;
    update({ sport: nextSport, id: next.id, fieldKey: next.fields[0].key, otherKey: next.fields[1]?.key || next.fields[0].key, group: "all", query: "", selectedId: null });
  };
  useEffect(() => {
    const restore = () => {
      setRestored(false);
      setViewState(readLabViewState(window.location.search, data));
    };
    restore();
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, [data]);
  useEffect(() => {
    if (!restored) {
      setRestored(true);
      return;
    }
    const url = new URL(window.location.href);
    url.search = labViewSearch(url.search, viewState);
    window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
  }, [restored, viewState]);
  const selected = filtered.find(row => row.id === selectedId) || null;
  const inspect = (row: LabRow) => { trigger.current = document.activeElement; update({ selectedId: row.id }); };
  const close = () => { update({ selectedId: null }); if (trigger.current instanceof HTMLElement || trigger.current instanceof SVGElement) trigger.current.focus(); };
  useEffect(() => { if (selected) inspector.current?.focus(); }, [selected]);
  return <div className="cv-workspace"><div className="cv-workspace-inner lab-page"><header className="cv-masthead"><div><p className="cv-eyebrow">CourtVision / Measurement lab</p><h1>Follow your curiosity into the data.</h1><p>Change the metric. Inspect the rows. Keep the evidence in view.</p></div><a className="cv-primary" href={`${base}/analytics/compare/`}>Compare profiles <ArrowUpRight size={16} /></a></header>
    <div className="lab-shell"><aside className="lab-sidebar"><label className="lab-field-label">Explore a sport<select value={sport} aria-label="Filter lab by sport" onChange={e => chooseSport(e.target.value as Sport)}>{SPORTS.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}</select></label>
      <label className="lab-field-label lab-dataset-picker">Dataset<select value={dataset.id} aria-label="Choose dataset" onChange={e => choose(e.target.value)}>{categories.map(category => <optgroup key={category} label={category}>{choices.filter(d => d.category === category).map(d => <option key={d.id} value={d.id}>{d.title}</option>)}</optgroup>)}</select></label>
      <div className="lab-dataset-catalog">{categories.map(category => <div key={category} className="lab-nav-group"><p className="cv-eyebrow">{category}</p>{choices.filter(d => d.category === category).map(d => { const count = rowsForSport(d, sport).length; return <button key={d.id} aria-pressed={dataset.id === d.id} onClick={() => choose(d.id)}><span>{d.title}</span><small>{count ? rowLabel(count) : "No qualifying rows"}</small></button>; })}</div>)}</div>
    </aside><div className="lab-main"><section className="cv-panel lab-analysis"><div className="lab-analysis-head"><div><span className="cv-badge">{dataset.status}</span><h2>{dataset.title}</h2><p className="cv-muted">{dataset.description}</p></div><a href={sourceUrl(dataset.source)} target="_blank" rel="noreferrer" className="cv-source">Source JSON <ArrowUpRight size={14} /></a></div>
      <div className="lab-controls"><label className="lab-field-label lab-primary-field">Primary measurement<select aria-label="Primary measurement" value={field.key} onChange={e => update({ fieldKey: e.target.value, selectedId: null })}>{dataset.fields.map(f => <option key={f.key} value={f.key}>{f.label}</option>)}</select></label><label className="lab-field-label">Published group<select aria-label="Published group" value={group} onChange={e => update({ group: e.target.value, selectedId: null })}><option value="all">All published groups</option>{groups.map(g => <option key={g}>{g}</option>)}</select></label><label className="lab-field-label">Rank order<select aria-label="Rank order" value={ascending ? "asc" : "desc"} onChange={e => update({ ascending: e.target.value === "asc" })}><option value="desc">Highest first</option><option value="asc">Lowest first</option></select></label></div>
      <div className="lab-chart-controls"><div><div className="cv-segment" aria-label="Measurement visualization">{[{ id: "rank", label: "Ranked bars" }, { id: "scatter", label: "Scatter plot" }, { id: "table", label: "Data table" }, { id: "distribution", label: "Distribution" }].map(m => <button key={m.id} aria-pressed={mode === m.id} onClick={() => update({ mode: m.id as LabViewState["mode"] })}>{m.label}</button>)}</div><p className="lab-readout"><b>{field.label}</b><span>{rowLabel(filtered.length)}; {ranked.length} numeric</span></p></div><button className="lab-export" onClick={() => exportLabCSV(dataset, filtered)} disabled={!filtered.length}><Download size={14} /> Export rows</button></div>
      <label className="cv-search"><Search size={16} /><input aria-label="Search measurement rows" placeholder="Find a player, team, or group in this dataset" value={query} onChange={e => update({ query: e.target.value, selectedId: null })} /></label>
      <p className="cv-result-count" role="status">{rowLabel(filtered.length)} {countVerb(filtered.length, "matches", "match")}; {ranked.length} {countVerb(ranked.length, "contains", "contain")} {field.label.toLowerCase()}.</p>
      {mode === "scatter" && <label className="lab-field-label lab-second-axis">Vertical measurement<select aria-label="Vertical measurement" value={other.key} onChange={e => update({ otherKey: e.target.value })}>{dataset.fields.map(f => <option key={f.key} value={f.key}>{f.label}</option>)}</select></label>}
      <DistributionSummary rows={filtered} field={field} />
      {!filtered.length ? <Empty>{dataset.sport === "all" && sport !== "all" && !sportRows.length ? `No published measurements for ${sportLabel} in this metric. The source's data gap is preserved.` : dataset.rows.length ? "No rows match this search and group." : "No qualifying measurements were published for this view. The source's data gap is preserved."}</Empty> : mode === "table" ? <LabTable dataset={dataset} rows={[...ranked, ...filtered.filter(r => !ranked.some(n => n.id === r.id))]} onSelect={inspect} /> : mode === "distribution" ? <DistributionPlot rows={filtered} field={field} /> : mode === "scatter" ? <ScatterPlot rows={filtered} x={field} y={other} onSelect={inspect} /> : ranked.length ? <RankedPlot rows={ranked} field={field} onSelect={inspect} /> : <Empty>Numeric measurements are unavailable or censored. The data table preserves those rows and their notes.</Empty>}
      {selected && <section ref={inspector} tabIndex={-1} className="lab-inspector" aria-label="Selected measurement" onKeyDown={e => { if (e.key === "Escape") close(); }}><button className="lab-close" aria-label="Close measurement details" onClick={close}><X size={16} /></button><p className="cv-eyebrow">{selected.group}</p><h3>{selected.label}</h3><dl>{dataset.fields.map(f => <div key={f.key}><dt>{f.label}</dt><dd>{display(selected.values[f.key], f)}</dd></div>)}</dl>{selected.note && <p>{selected.note}</p>}</section>}
    </section><section className="lab-evidence-note"><SlidersHorizontal size={19} /><div><h3>Read the measurement in context</h3><p>{dataset.scope}</p><p>{dataset.caveat}</p><a href={moduleUrl(dataset.source)}>Full method and source artifact <ArrowUpRight size={13} /></a></div></section>
    <section className="cv-panel lab-novel-index"><p className="cv-eyebrow">Published experimental metrics</p><h2>Six lenses, with the assumptions attached.</h2><p className="cv-muted">These are the project's published metric formulations. Prior-art labels include incremental contributions and novel packaging; inclusion does not establish universal originality or predictive value.</p><div>{data.novel.map(n => <article key={n.module}><b>{n.abbrev}</b><h3><a href={moduleUrl(n.module)}>{n.stat_name}</a></h3><span className="cv-badge">{n.is_honest_null ? "Honest null" : humanize(n.prior_art_verdict)}</span><p>{n.headline}</p><details><summary>View formula</summary><code>{n.formula}</code></details></article>)}</div></section>
    </div></div></div></div>;
}
