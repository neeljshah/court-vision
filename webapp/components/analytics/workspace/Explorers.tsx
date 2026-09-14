"use client";
import { useState } from "react";
import { ArrowUpRight, Search } from "lucide-react";
import { base, dateLabel, humanize, moduleUrl, number, type Entity, type Module, type Sport } from "@/lib/analytics/dashboardTypes";
import { Empty, Pagination, Panel } from "./Primitives";

export function Catalog({ modules }: { modules: Module[] }) {
  const [query, setQuery] = useState(""); const [category, setCategory] = useState("all"); const [page, setPage] = useState(0);
  const filtered = modules.filter(m => (category === "all" || m.category === category) && `${m.title} ${m.id} ${m.description}`.toLowerCase().includes(query.toLowerCase()));
  return <Panel title="Explore the published source modules" eyebrow={`${modules.length} published modules / all sports`} source="site_manifest">
    <a className="cv-text-button" href={`${base}/analytics/browse/`}>Open the full library, including derived analyses <ArrowUpRight size={15} /></a>
    <p className="cv-muted">Search player development, matchup context, calibration and novel statistics. Categories describe subject matter, not validation status.</p>
    <div className="cv-filter-row"><label className="cv-search"><Search size={17} /><input aria-label="Search analytics modules" placeholder="Try calibration, lineup, tennis..." value={query} onChange={e => { setQuery(e.target.value); setPage(0); }} /></label><select aria-label="Module category" value={category} onChange={e => { setCategory(e.target.value); setPage(0); }}><option value="all">All categories</option>{Array.from(new Set(modules.map(m => m.category))).sort().map(c => <option key={c}>{c}</option>)}</select></div>
    <p className="cv-result-count" role="status">{filtered.length} matching modules</p><div className="cv-catalog">{filtered.slice(page * 12, page * 12 + 12).map(m => <a className="cv-module" href={moduleUrl(m.id)} key={m.id}><div><span className="cv-eyebrow">{m.category}</span><ArrowUpRight size={17} /></div><h3>{m.title}</h3><p>{m.description && m.description !== "DESCRIPTIVE_ONLY" ? m.description : "Explore the published measurements, methodology, and source artifact for this analysis."}</p><footer><span className="cv-badge">{m.status === "ok" ? "Snapshot available" : humanize(m.status)}</span><span>{dateLabel(m.asOf)}</span></footer></a>)}</div>
    {!filtered.length && <Empty>No matching modules. Try another topic or category.</Empty>}<Pagination page={page} total={filtered.length} onChange={setPage} />
  </Panel>;
}
function metricValue(label: string, value: number) {
  if (/wr_career/.test(label)) return `${(value * 100).toFixed(1)}%`;
  if (/velo/.test(label)) return `${value.toFixed(1)} mph`;
  return Number.isInteger(value) ? number(value) : value.toFixed(/ece/.test(label) ? 4 : 2);
}
const labels: Record<string, string> = { corpus_pts_per36: "Points / 36", corpus_ast_per36: "Assists / 36", corpus_games: "Corpus games", ppg_latest_season: "Points / game", pace_proxy_latest_season: "Pace proxy", avg_exit_velo: "Exit velocity", pitches_faced: "Pitches faced", ppg_l10: "Points / game (L10)", gd_l10: "Goal difference (L10)", hard_wr_career: "Hard win rate", clay_wr_career: "Clay win rate", velo_p50: "Median velocity", n_pitches: "Pitches", top_pitch_type_pct: "Top pitch share (%)", model_ece: "Model ECE", market_ece: "Market ECE" };
export function Entities({ entities, sport }: { entities: Entity[]; sport: Sport }) {
  const [query, setQuery] = useState(""); const [page, setPage] = useState(0);
  const filtered = entities.filter(e => (sport === "all" || e.sport === sport) && `${e.name} ${e.pack}`.toLowerCase().includes(query.toLowerCase())).sort((a, b) => a.name.localeCompare(b.name));
  const safePage = Math.min(page, Math.max(0, Math.ceil(filtered.length / 12) - 1));
  return <Panel title="Find a player, team, or profile" eyebrow="Entity atlas">
    <p className="cv-muted">Open a profile for its statistical card and available comparisons. Career fields may cover only the seasons collected in the corpus.</p>
    <label className="cv-search cv-entity-search"><Search size={17} /><input aria-label="Search entities" placeholder="Search a player, team, or entity pack..." value={query} onChange={e => { setQuery(e.target.value); setPage(0); }} /></label>
    <p className="cv-result-count" role="status">{number(filtered.length)} matching profiles</p><div className="cv-entities">{filtered.slice(safePage * 12, safePage * 12 + 12).map(e => <a href={`${base}/analytics/players/${e.pack}/${e.slug}/`} className="cv-entity" key={`${e.pack}/${e.slug}`}><div className="cv-entity-top"><span className="cv-monogram">{e.name.split(/\s+/).slice(0, 2).map(n => n[0]).join("")}</span><ArrowUpRight size={16} /></div><span className="cv-eyebrow">{humanize(e.pack)}</span><h3>{e.name}</h3><dl>{e.metrics.slice(0, 2).map(m => <div key={m.label}><dt>{labels[m.label] || humanize(m.label)}</dt><dd>{metricValue(m.label, m.value)}</dd></div>)}</dl><span className="cv-entity-date">As of {dateLabel(e.asOf)}</span></a>)}</div>
    {!filtered.length && <Empty>No profiles match. Try a surname or switch to all sports.</Empty>}<Pagination page={safePage} total={filtered.length} onChange={setPage} />
  </Panel>;
}
