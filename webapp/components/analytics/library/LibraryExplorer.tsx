"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowDown, ArrowUpRight, Search, SlidersHorizontal, Layers3 } from "lucide-react";
import { SPORTS, type Sport } from "@/lib/analytics/dashboardTypes";
import { filterLibrary, type LibraryEntry } from "@/lib/analytics/libraryTypes";
import { collectionMemberIds, readingCollections } from "@/lib/analytics/readingCollections";
import { libraryViewSearch, readLibraryViewState, type LibraryViewState } from "@/lib/analytics/libraryViewState";

function MeasurementPreview({ values, label }: { values: number[]; label: string }) {
  if (!values.length) return <div className="library-source-preview"><Layers3 size={25} /><span>Published source module</span></div>;
  const lo = Math.min(0, ...values), hi = Math.max(0, ...values), span = hi - lo || 1, zero = 53 - (-lo / span) * 46;
  return <div className="library-preview"><svg viewBox="0 0 272 60" role="img" aria-label={`${label}: preview of ${values.length} published rows in source order`}>
    <line x1="0" x2="272" y1={zero} y2={zero} stroke="currentColor" opacity=".2" />
    {values.map((v, i) => { const y = 53 - ((v - lo) / span) * 46; return <rect key={i} x={i * (272 / values.length) + 2} y={Math.min(y, zero)} width={Math.max(2, 272 / values.length - 5)} height={Math.max(1, Math.abs(y - zero))} rx="1" fill="currentColor" opacity={.45 + i / values.length * .5} />; })}
  </svg><span>{label} / source-order preview</span></div>;
}

function SourceEvidence({ entry }: { entry: LibraryEntry }) {
  const summary = entry.sourceSummary;
  if (!summary) return null;
  return <div className="library-source-evidence">
    <div className="library-source-date"><span>Snapshot</span><time>{entry.asOf || "Date not published"}</time>{summary.availability !== "published" && <b>{summary.availability}</b>}</div>
    <p className="library-source-scope">{summary.scope}</p>
    {summary.measurements.length > 0 && <dl className="library-measurements">{summary.measurements.slice(0, 3).map(item => <div key={item.label}><dt>{item.label}</dt><dd>{item.value}</dd></div>)}</dl>}
    {summary.previewRows[0] && <dl className="library-labelled-preview">{summary.previewRows[0].slice(0, 3).map(item => <div key={item.label}><dt>{item.label}</dt><dd>{item.value}</dd></div>)}</dl>}
  </div>;
}

function DerivedEvidence({ entry }: { entry: LibraryEntry }) {
  return <div className="library-source-evidence"><div className="library-source-date"><span>Snapshot</span><time>{entry.asOf || "Date not published"}</time></div></div>;
}

export default function LibraryExplorer({ entries }: { entries: LibraryEntry[] }) {
  const [state, setState] = useState<LibraryViewState>({ sport: "all", kind: "all", query: "", collection: "all", page: 1 });
  const { sport, kind, query, collection, page } = state;
  useEffect(() => {
    const restore = () => setState(readLibraryViewState(window.location.search));
    restore(); window.addEventListener("popstate", restore); return () => window.removeEventListener("popstate", restore);
  }, []);
  function writeState(next: LibraryViewState) {
    setState(next);
    const search = libraryViewSearch(window.location.search, next);
    window.history.replaceState(null, "", `${window.location.pathname}${search ? `?${search}` : ""}`);
  }
  function update(s: Sport, k: LibraryViewState["kind"], q: string, c: string = collection) {
    writeState({ sport: s, kind: k, query: q, collection: c, page: 1 });
  }
  function updatePage(nextPage: number) {
    writeState({ ...state, page: nextPage });
  }
  const collectionIds = collectionMemberIds(collection);
  const matched = filterLibrary(entries, sport, kind, query, collectionIds), pages = Math.max(1, Math.ceil(matched.length / 12)), safePage = page <= pages ? page : 1, visible = matched.slice((safePage - 1) * 12, safePage * 12);
  const derived = entries.filter(e => e.kind === "derived"), sources = entries.filter(e => e.kind === "source");
  return <div className="cv-workspace library-page"><div className="cv-workspace-inner">
    <header className="library-hero"><div><p className="cv-eyebrow">CourtVision / Intelligence library</p><h1>Sports analyses<br /><em>and their source data.</em></h1><p>Choose an analysis, inspect its calculation, and download its rows.</p><a href="#library-results" className="library-hero-action">Explore the library <ArrowDown size={17} /></a></div>
      <div className="library-hero-index"><span>THE COLLECTION</span><strong>{entries.length}</strong><p>{sources.length} published source modules<br />{derived.length} derived analyses</p><div><span>04 sports</span><span>Sources included</span></div></div>
    </header>
    <div className="library-journeys"><Link href="/analytics/compare/"><span>01 / MATCHUPS</span><strong>Compare two profiles <ArrowUpRight size={18} /></strong></Link><Link href="/analytics/research/nba-matchup-profile-contrast/"><span>02 / HISTORICAL NBA</span><strong>Explore 435 team pairings <ArrowUpRight size={18} /></strong></Link><Link href="/analytics/ask/"><span>03 / ASK SCOUT</span><strong>Start with your own question <ArrowUpRight size={18} /></strong></Link></div>
    <section id="library-results" className="library-catalog" aria-label="Browse analytics">
      <div className="library-toolbar"><div><p className="cv-eyebrow"><SlidersHorizontal size={13} /> Browse by question</p><h2>The analytics collection</h2></div><label className="library-search"><Search size={17} /><span className="sr-only">Search analytics library</span><input value={query} onChange={e => update(sport, kind, e.target.value)} placeholder="Search a metric, formula, or question" /></label></div>
      <div className="library-question-collections" aria-label="Question-led collections">{readingCollections.map(item => <button key={item.id} aria-pressed={collection === item.id} onClick={() => update(sport, kind, query, collection === item.id ? "all" : item.id)}><span>{item.title}</span><small>{collectionMemberIds(item.id).length} readings</small><p>{item.description}</p></button>)}</div>
      <div className="library-filters"><div className="cv-sports" aria-label="Library sport">{SPORTS.map(s => <button key={s.id} aria-pressed={sport === s.id} onClick={() => update(s.id, kind, query)}>{s.label}</button>)}</div><label>Entry type<select value={kind} onChange={e => update(sport, e.target.value as LibraryViewState["kind"], query)}><option value="all">All entries</option><option value="derived">Derived analyses</option><option value="source">Source modules</option><option value="finding">Findings</option><option value="inspector">Inspectors</option><option value="explainer">Explainers</option></select></label></div>
      <div className="library-count"><p role="status">{matched.length} {matched.length === 1 ? "entry" : "entries"}{collection !== "all" ? " in this question" : ""}{sport !== "all" ? " including checks used across sports" : ""}{query ? ` matching "${query}"` : ""}</p><span>Derived analyses use published snapshots; methods remain inspectable.</span></div>
      {visible.length ? <div className="library-grid">{visible.map(e => <Link href={e.href} key={`${e.kind}-${e.id}`} className={`library-card library-card-${e.kind}`}><div className="library-card-meta"><span>{e.sport === "all" ? "Shared / cross-sport" : e.sport.toUpperCase()}</span><span>{e.kindLabel}</span></div><h3>{e.title}</h3><p>{e.description}</p>{e.kind === "source" ? <SourceEvidence entry={e} /> : e.kind === "derived" ? <><DerivedEvidence entry={e} /><MeasurementPreview values={e.preview} label={e.previewLabel} /></> : <DerivedEvidence entry={e} />}<div className="library-card-footer"><span>{e.rows === null ? e.status.replace(/_/g, " ") : `${e.rows.toLocaleString("en-US")} rows / ${e.fields} fields`}</span><ArrowUpRight size={19} /></div></Link>)}</div> : <div className="cv-empty">No analytics match these filters. Try fewer search terms or another collection.<button onClick={() => update("all", "all", "", "all")}>Reset filters</button></div>}
      <nav className="library-pagination" aria-label="Library pages"><button onClick={() => updatePage(Math.max(1, safePage - 1))} disabled={safePage === 1}>Previous</button><span>Page {safePage} of {pages}</span><button onClick={() => updatePage(Math.min(pages, safePage + 1))} disabled={safePage >= pages}>Next</button></nav>
    </section>
  </div></div>;
}
