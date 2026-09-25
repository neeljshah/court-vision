"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowUpRight, Download, Search, SlidersHorizontal, X } from "lucide-react";
import { base, humanize, moduleUrl, sourceUrl, SPORTS, type Sport } from "@/lib/analytics/dashboardTypes";
import { displayMeasurement as display, rankedRows, type LabData, type LabRow } from "@/lib/analytics/labTypes";
import { DistributionSummary, DistributionPlot } from "./DistributionSummary";
import { MeasurementPosition } from "./MeasurementPosition";
import { RankedPlot, ScatterPlot } from "./LabPlot";
import { LabTable, exportLabCSV } from "./LabTable";
import { Empty } from "@/components/analytics/workspace/Primitives";
import { defaultLabMode, labViewSearch, readLabViewState, type LabViewState } from "./labViewState";
import { LabComparisonContext } from "./LabComparisonContext";
import { labComparisonPolicy, matchesLabCohort } from "@/lib/analytics/labComparisonPolicy";
import { noticesForModules } from "@/lib/analytics/dataIntegrity";
import { DataIntegrityNotice } from "@/components/analytics/DataIntegrityNotice";

const sportGroup = (sport: Sport) => sport === "soccer" ? "INTERNATIONAL SOCCER" : sport.toUpperCase();
const rowLabel = (count: number) => `${count} published ${count === 1 ? "row" : "rows"}`;
const rowsForSport = (dataset: LabData["datasets"][number], sport: Sport) =>
  dataset.sport === "all" && sport !== "all" ? dataset.rows.filter(r => r.group === sportGroup(sport)) : dataset.rows;

export default function MeasurementLab({ data }: { data: LabData }) {
  const [viewState, setViewState] = useState<LabViewState>(() => readLabViewState("", data));
  const [restored, setRestored] = useState(false);
  const inspector = useRef<HTMLElement>(null), trigger = useRef<Element | null>(null);
  const { id, sport, fieldKey, otherKey, mode, query, group, ascending, selectedId, cohort: selectedCohortKey, allCohorts } = viewState;
  const update = (change: Partial<LabViewState>) => setViewState(current => ({ ...current, ...change }));
  const dataset = data.datasets.find(d => d.id === id) || data.datasets[0];
  const field = dataset.fields.find(f => f.key === fieldKey) || dataset.fields[0];
  const other = dataset.fields.find(f => f.key === otherKey) || dataset.fields[1] || field;
  const sportRows = rowsForSport(dataset, sport);
  const comparison = labComparisonPolicy(sportRows);
  const activeCohort = comparison.cohorts.find(cohort => cohort.key === selectedCohortKey) || comparison.cohorts.find(cohort => cohort.compatibility === "compatible") || comparison.cohorts[0];
  const showAllCohorts = comparison.compatibility !== "compatible" && allCohorts;
  const cohortRows = showAllCohorts ? sportRows : activeCohort ? sportRows.filter(row => matchesLabCohort(row, activeCohort)) : sportRows;
  const groups = Array.from(new Set(sportRows.map(r => r.group)));
  const groupRows = comparison.compatibility === "compatible" ? sportRows.filter(r => group === "all" || r.group === group) : cohortRows;
  const filtered = groupRows.filter(r => `${r.label} ${r.group} ${r.note || ""}`.toLowerCase().includes(query.toLowerCase()));
  const ranked = rankedRows(filtered, field.key, ascending);
  const selectedCompatibility = showAllCohorts ? "unknown" : activeCohort?.compatibility || "unknown";
  const suppressPooledSummaries = selectedCompatibility !== "compatible";
  const censoredLabels = filtered.filter(row => row.note?.includes("(censored)")).map(row => `${row.label}: ${row.note?.match(/Half-life label: (.*?)(?:\. Window:|\.$)/)?.[1] || "censored"}`);
  const choices = data.datasets.filter(d => sport === "all" || d.sport === sport || d.sport === "all");
  const categories = Array.from(new Set(choices.map(d => d.category)));
  const sportLabel = SPORTS.find(s => s.id === sport)?.label || sport;
  const populationSportLabel = SPORTS.find(s => s.id === (sport === "all" ? dataset.sport : sport))?.label || sportLabel;
  const integrityNotices = noticesForModules([dataset.source]);
  const choose = (value: string) => {
    const next = data.datasets.find(d => d.id === value) || data.datasets[0];
    const nextMode = defaultLabMode(labComparisonPolicy(rowsForSport(next, sport)), null, false);
    update({ id: next.id, fieldKey: next.fields[0].key, otherKey: next.fields[1]?.key || next.fields[0].key, query: "", group: "all", selectedId: null, cohort: null, allCohorts: false, ...(nextMode === "table" ? { mode: "table" as const } : {}) });
  };
  const chooseSport = (nextSport: Sport) => {
    const compatible = data.datasets.find(d => nextSport === "all" || d.sport === nextSport || d.sport === "all");
    const next = compatible && (dataset.sport !== nextSport && dataset.sport !== "all") ? compatible : dataset;
    const nextMode = defaultLabMode(labComparisonPolicy(rowsForSport(next, nextSport)), null, false);
    update({ sport: nextSport, id: next.id, fieldKey: next.fields[0].key, otherKey: next.fields[1]?.key || next.fields[0].key, group: "all", query: "", selectedId: null, cohort: null, allCohorts: false, ...(nextMode === "table" ? { mode: "table" as const } : {}) });
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
  return <div className="cv-workspace"><div className="cv-workspace-inner lab-page"><header className="cv-masthead"><div><p className="cv-eyebrow">CourtVision / Measurement lab</p><h1>Explore the published measurements.</h1><p>Compare measurements, inspect rows, and export your selection.</p></div><a className="cv-primary" href={`${base}/analytics/compare/`}>Compare profiles <ArrowUpRight size={16} /></a></header>
    <div className="lab-shell"><aside className="lab-sidebar"><label className="lab-field-label">Explore a sport<select value={sport} aria-label="Filter lab by sport" onChange={e => chooseSport(e.target.value as Sport)}>{SPORTS.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}</select></label>
      <label className="lab-field-label lab-dataset-picker">Dataset<select value={dataset.id} aria-label="Choose dataset" onChange={e => choose(e.target.value)}>{categories.map(category => <optgroup key={category} label={category}>{choices.filter(d => d.category === category).map(d => <option key={d.id} value={d.id}>{d.title}{!d.rows.length ? " (no qualifying rows)" : ""}</option>)}</optgroup>)}</select></label>
      <div className="lab-dataset-catalog">{categories.map(category => <div key={category} className="lab-nav-group"><p className="cv-eyebrow">{category}</p>{choices.filter(d => d.category === category).map(d => { const count = rowsForSport(d, sport).length; return <button key={d.id} aria-pressed={dataset.id === d.id} onClick={() => choose(d.id)}><span>{d.title}</span><small>{count ? rowLabel(count) : "No qualifying rows"}</small></button>; })}</div>)}</div>
    </aside><div className="lab-main"><section className="cv-panel lab-analysis"><div className="lab-analysis-head"><div><span className="cv-badge">{dataset.status}</span><h2>{dataset.title}</h2><p className="cv-muted">{dataset.description}</p></div><a href={sourceUrl(dataset.source)} target="_blank" rel="noreferrer" className="cv-source">Source JSON <ArrowUpRight size={14} /></a></div>
      <DataIntegrityNotice notices={integrityNotices} moduleIds={[dataset.source]} />
      <div className="lab-controls"><label className="lab-field-label lab-primary-field">Primary measurement<select aria-label="Primary measurement" value={field.key} onChange={e => update({ fieldKey: e.target.value, selectedId: null })}>{dataset.fields.map(f => <option key={f.key} value={f.key}>{f.label}</option>)}</select></label><label className="lab-field-label">Published group<select aria-label="Published group" value={comparison.compatibility === "compatible" ? group : showAllCohorts ? "all" : activeCohort?.key || ""} onChange={e => { if (comparison.compatibility === "compatible") update({ group: e.target.value, selectedId: null }); else if (e.target.value === "all") update({ group: "all", selectedId: null, cohort: null, allCohorts: true, mode: "table" }); else update({ group: "all", selectedId: null, cohort: e.target.value, allCohorts: false, ...(comparison.cohorts.find(cohort => cohort.key === e.target.value)?.compatibility !== "compatible" ? { mode: "table" as const } : {}) }); }}>
        {comparison.compatibility === "compatible" ? <><option value="all">All published groups</option>{groups.map(g => <option key={g}>{g}</option>)}</> : <><option value="all">Show all cohorts (not comparable)</option>{comparison.cohorts.map(cohort => <option key={cohort.key} value={cohort.key}>{cohort.label}</option>)}</>}</select></label><label className="lab-field-label">Rank order<select aria-label="Rank order" value={suppressPooledSummaries ? "source" : ascending ? "asc" : "desc"} disabled={suppressPooledSummaries} onChange={e => update({ ascending: e.target.value === "asc" })}>{suppressPooledSummaries ? <option value="source">Published source order</option> : <><option value="desc">Highest first</option><option value="asc">Lowest first</option></>}</select></label></div>
      {comparison.compatibility !== "compatible" && <section className="lab-cohort-notice" aria-label="Cohort comparison notice"><p>{comparison.reason} {showAllCohorts ? "All cohorts are shown without a pooled ranking or median." : selectedCompatibility === "unknown" ? "The selected cohort has no complete published definition, so rankings and summaries are unavailable." : `Showing ${activeCohort?.label || "one cohort"} by default.`}</p><ul>{comparison.cohorts.map(cohort => <li key={cohort.key}><b>{cohort.label}</b><span>{rowLabel(cohort.rowCount)}</span></li>)}</ul></section>}
      <div className="lab-chart-controls"><div><div className="cv-segment" role="group" aria-label="Measurement visualization">{[{ id: "rank", label: "Ranked bars" }, { id: "scatter", label: "Scatter plot" }, { id: "table", label: "Data table" }, { id: "distribution", label: "Distribution" }].map(m => <button key={m.id} aria-pressed={mode === m.id} onClick={() => update({ mode: m.id as LabViewState["mode"] })}>{m.label}</button>)}</div><p className="lab-readout"><b>{field.label}</b><span>{rowLabel(filtered.length)}; {ranked.length} numeric</span></p></div><button className="lab-export" onClick={() => exportLabCSV(dataset, filtered)} disabled={!filtered.length}><Download size={14} /> Export rows</button></div>
      <LabComparisonContext rows={filtered} />
      {censoredLabels.length > 0 && <p className="lab-censored-labels">Published censored half-life rows retained in the table: {censoredLabels.join("; ")}. They are excluded from numeric ranking.</p>}
      <label className="cv-search"><Search size={16} /><input aria-label="Search measurement rows" placeholder="Find a player, team, or group in this dataset" value={query} onChange={e => update({ query: e.target.value, selectedId: null })} /></label>
      <p className="cv-result-count" role="status" aria-live="polite">{query ? `${filtered.length} of ${groupRows.length} rows match "${query}"` : `${groupRows.length} ${groupRows.length === 1 ? "row" : "rows"}`}</p>
      {mode === "scatter" && <label className="lab-field-label lab-second-axis">Vertical measurement<select aria-label="Vertical measurement" value={other.key} onChange={e => update({ otherKey: e.target.value })}>{dataset.fields.map(f => <option key={f.key} value={f.key}>{f.label}</option>)}</select></label>}
      {!suppressPooledSummaries && mode !== "scatter" && <DistributionSummary rows={filtered} field={field} />}
      {!filtered.length ? dataset.rows.length === 0 ? <Empty><p>No qualifying rows were published for this dataset.</p><p>{dataset.eligiblePopulation != null ? `Eligible population: ${dataset.eligiblePopulation}. ` : ""}{dataset.qualificationRule ? `Qualification rule: ${dataset.qualificationRule}. ` : ""}{dataset.nQualifying != null ? `Qualifying rows: ${dataset.nQualifying}.` : ""}</p>{dataset.note ? <p>{dataset.note}</p> : null}<Link href="/analytics/research/tennis-surface-support" prefetch={false}>Read the tennis surface-support analysis</Link></Empty> : <Empty>{dataset.sport === "all" && sport !== "all" && !sportRows.length ? `No published measurements for ${sportLabel} in this metric. The source's data gap is preserved.` : <><p>No rows match this search and group.</p><button type="button" onClick={() => update({ query: "", group: "all", selectedId: null })}>Clear search and group</button></>}</Empty> : suppressPooledSummaries && mode !== "table" ? <Empty>Rankings, distributions, and relative positions require a complete published cohort definition. The data table remains available.</Empty> : mode === "table" ? <LabTable key={JSON.stringify([dataset.id, sport, field.key, group, activeCohort?.key, showAllCohorts, query, ascending])} dataset={dataset} rows={suppressPooledSummaries ? filtered : [...ranked, ...filtered.filter(r => !ranked.some(n => n.id === r.id))]} onSelect={inspect} /> : mode === "distribution" ? <DistributionPlot rows={filtered} field={field} /> : mode === "scatter" ? <ScatterPlot rows={filtered} x={field} y={other} onSelect={inspect} /> : ranked.length ? <RankedPlot rows={ranked} field={field} onSelect={inspect} /> : <Empty>Numeric measurements are unavailable or censored. The data table preserves those rows and their notes.</Empty>}
      {selected && <section ref={inspector} tabIndex={-1} className="lab-inspector" aria-label="Selected measurement" onKeyDown={e => { if (e.key === "Escape") close(); }}><button className="lab-close" aria-label="Close measurement details" onClick={close}><X size={16} /></button><p className="cv-eyebrow">{selected.group}</p><h3>{selected.label}</h3><dl>{dataset.fields.map(f => <div key={f.key}><dt>{f.label}</dt><dd>{display(selected.values[f.key], f)}</dd></div>)}</dl>{selected.note && <p>{selected.note}</p>}{suppressPooledSummaries ? <p className="measurement-position-note">A complete published cohort definition is required for measurement context.</p> : <MeasurementPosition rows={groupRows} field={field} selected={selected} populationLabel={comparison.compatible ? `${populationSportLabel} / ${group === "all" ? "All published groups" : group}` : activeCohort?.label || "Selected cohort"} />}</section>}
    </section><section className="lab-evidence-note"><SlidersHorizontal size={19} /><div><h3>Read the measurement in context</h3><p>{dataset.scope}</p><p>{dataset.caveat}</p><a href={moduleUrl(dataset.source)}>Full method and source artifact <ArrowUpRight size={13} /></a></div></section>
    <section className="cv-panel lab-novel-index"><p className="cv-eyebrow">Published experimental metrics</p><h2>Six experimental measurements and their definitions.</h2><p className="cv-muted">These are the project's published metric formulations. Prior-art labels include incremental contributions and novel packaging; inclusion does not establish universal originality or predictive value.</p><div>{data.novel.map(n => <article key={n.module}><DataIntegrityNotice notices={noticesForModules([n.module])} moduleIds={[n.module]} /><b>{n.abbrev}</b><h3><a href={moduleUrl(n.module)}>{n.stat_name}</a></h3><span className="cv-badge">{n.is_honest_null ? "Honest null" : humanize(n.prior_art_verdict)}</span><p>{n.headline}</p><details><summary>View formula</summary><code>{n.formula}</code></details></article>)}</div></section>
    </div></div></div></div>;
}
