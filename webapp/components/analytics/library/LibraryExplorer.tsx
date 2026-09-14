"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowDown, ArrowUpRight, Search, SlidersHorizontal, Layers3 } from "lucide-react";
import { SPORTS, type Sport } from "@/lib/analytics/dashboardTypes";
import { filterLibrary, type LibraryEntry } from "@/lib/analytics/libraryTypes";

function MeasurementPreview({ values, label }: { values: number[]; label: string }) {
  if (!values.length) return <div className="library-source-preview"><Layers3 size={25} /><span>Published source module</span></div>;
  const lo = Math.min(0, ...values), hi = Math.max(0, ...values), span = hi - lo || 1, zero = 53 - (-lo / span) * 46;
  return <div className="library-preview"><svg viewBox="0 0 272 60" role="img" aria-label={`${label}: preview of ${values.length} published rows in source order`}>
    <line x1="0" x2="272" y1={zero} y2={zero} stroke="currentColor" opacity=".2" />
    {values.map((v, i) => { const y = 53 - ((v - lo) / span) * 46; return <rect key={i} x={i * (272 / values.length) + 2} y={Math.min(y, zero)} width={Math.max(2, 272 / values.length - 5)} height={Math.max(1, Math.abs(y - zero))} rx="1" fill="currentColor" opacity={.45 + i / values.length * .5} />; })}
  </svg><span>{label} / source-order preview</span></div>;
}

export default function LibraryExplorer({ entries }: { entries: LibraryEntry[] }) {
  const [sport, setSport] = useState<Sport>("all"), [kind, setKind] = useState("all"), [query, setQuery] = useState(""), [page, setPage] = useState(0);
  useEffect(() => {
    const restore = () => { const p = new URLSearchParams(window.location.search), s = p.get("sport"); setSport(SPORTS.some(x => x.id === s) ? s as Sport : "all"); setKind(["derived", "source"].includes(p.get("kind") || "") ? p.get("kind")! : "all"); setQuery(p.get("q") || ""); setPage(0); };
    restore(); window.addEventListener("popstate", restore); return () => window.removeEventListener("popstate", restore);
  }, []);
  function update(s: Sport, k: string, q: string) {
    setSport(s); setKind(k); setQuery(q); setPage(0);
    const p = new URLSearchParams(); if (s !== "all") p.set("sport", s); if (k !== "all") p.set("kind", k); if (q) p.set("q", q);
    window.history.replaceState(null, "", `${window.location.pathname}${p.size ? `?${p}` : ""}`);
  }
  const matched = filterLibrary(entries, sport, kind, query), pages = Math.max(1, Math.ceil(matched.length / 12)), safePage = Math.min(page, pages - 1), visible = matched.slice(safePage * 12, safePage * 12 + 12);
  const derived = entries.filter(e => e.kind === "derived");
  return <div className="cv-workspace library-page"><div className="cv-workspace-inner">
    <header className="library-hero"><div><p className="cv-eyebrow">CourtVision / Intelligence library</p><h1>More ways to<br /><em>read the game.</em></h1><p>Follow a question from the first comparison to the formula and the rows behind it.</p><a href="#library-results" className="library-hero-action">Explore the library <ArrowDown size={17} /></a></div>
      <div className="library-hero-index"><span>THE COLLECTION</span><strong>{entries.length}</strong><p>{entries.length - derived.length} published source modules<br />{derived.length} derived analyses</p><div><span>04 sports</span><span>Sources included</span></div></div>
    </header>
    <div className="library-journeys"><Link href="/analytics/compare/"><span>01 / MATCHUPS</span><strong>Put two profiles in perspective <ArrowUpRight size={18} /></strong></Link><Link href="/analytics/research/nba-matchup-profile-contrast/"><span>02 / HISTORICAL NBA</span><strong>Explore 435 team pairings <ArrowUpRight size={18} /></strong></Link><Link href="/analytics/ask/"><span>03 / ASK SCOUT</span><strong>Start with your own question <ArrowUpRight size={18} /></strong></Link></div>
    <section id="library-results" className="library-catalog" aria-label="Browse analytics">
      <div className="library-toolbar"><div><p className="cv-eyebrow"><SlidersHorizontal size={13} /> Find your next investigation</p><h2>The analytics collection</h2></div><label className="library-search"><Search size={17} /><span className="sr-only">Search analytics library</span><input value={query} onChange={e => update(sport, kind, e.target.value)} placeholder="Search a metric, formula, or question" /></label></div>
      <div className="library-filters"><div className="cv-sports" aria-label="Library sport">{SPORTS.map(s => <button key={s.id} aria-pressed={sport === s.id} onClick={() => update(s.id, kind, query)}>{s.label}</button>)}</div><label>Collection<select value={kind} onChange={e => update(sport, e.target.value, query)}><option value="all">All entries</option><option value="derived">Derived analyses</option><option value="source">Source modules</option></select></label></div>
      <div className="library-count"><p role="status">{matched.length} {matched.length === 1 ? "entry" : "entries"}{sport !== "all" ? " including shared diagnostics" : ""}{query ? ` matching "${query}"` : ""}</p><span>Derived analyses use published snapshots; methods remain inspectable.</span></div>
      {visible.length ? <div className="library-grid">{visible.map(e => <Link href={e.href} key={`${e.kind}-${e.id}`} className={`library-card library-card-${e.kind}`}><div className="library-card-meta"><span>{e.sport === "all" ? "Shared / cross-sport" : e.sport.toUpperCase()}</span><span>{e.kind === "derived" ? "Derived analysis" : "Source module"}</span></div><h3>{e.title}</h3><p>{e.description}</p><MeasurementPreview values={e.preview} label={e.previewLabel} /><div className="library-card-footer"><span>{e.rows === null ? e.status.replace(/_/g, " ") : `${e.rows.toLocaleString("en-US")} rows / ${e.fields} fields`}</span><ArrowUpRight size={19} /></div></Link>)}</div> : <div className="cv-empty">No analytics match these filters. Try fewer search terms or another collection.<button onClick={() => update("all", "all", "")}>Reset filters</button></div>}
      <nav className="library-pagination" aria-label="Library pages"><button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={!safePage}>Previous</button><span>Page {safePage + 1} of {pages}</span><button onClick={() => setPage(p => Math.min(pages - 1, p + 1))} disabled={safePage + 1 >= pages}>Next</button></nav>
    </section>
  </div></div>;
}
