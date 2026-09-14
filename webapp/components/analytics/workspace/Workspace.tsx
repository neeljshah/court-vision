"use client";
import { useState } from "react";
import { ArrowRight, ArrowUpRight, BookOpen, ChartNoAxesCombined, Database, FlaskConical, Layers3, Users } from "lucide-react";
import { base, number, SPORTS, type DashboardData, type Sport } from "@/lib/analytics/dashboardTypes";
import { Catalog, Entities } from "./Explorers";
import { Quality } from "./Quality";
import { Research } from "./Research";
import { Coverage } from "./Coverage";
import { Panel } from "./Primitives";
import { Benchmarks, WalkForward } from "./Benchmarks";
import { WorkspaceIntro } from "./WorkspaceIntro";

const views = [ { id: "overview", label: "Overview", Icon: ChartNoAxesCombined }, { id: "quality", label: "Model quality", Icon: Layers3 }, { id: "research", label: "Research ledger", Icon: FlaskConical }, { id: "entities", label: "Entity atlas", Icon: Users }, { id: "coverage", label: "Data coverage", Icon: Database }, { id: "library", label: "All analytics", Icon: BookOpen } ];
export default function Workspace({ data }: { data: DashboardData }) {
  const [sport, setSport] = useState<Sport>("all"); const [view, setActiveView] = useState("overview");
  const setView = (id: string) => { setActiveView(id); if (id === "library") setSport("all"); };
  const records = data.mechanisms.filter(m => sport === "all" || m.sport === sport);
  const entities = data.entities.filter(e => sport === "all" || e.sport === sport);
  return <div className="cv-workspace cv-overview"><div className="cv-workspace-inner">
    <WorkspaceIntro />
    <div className="cv-controls"><div className="cv-sports" aria-label="Filter analytics by sport">{SPORTS.map(s => <button key={s.id} onClick={() => setSport(s.id)} aria-pressed={sport === s.id} disabled={view === "library"}>{s.label}</button>)}</div><span className="cv-snapshot"><span />Historical snapshots <b>2026</b></span></div>
    <div className="cv-stat-grid"><button onClick={() => setView("entities")}><Users size={18} /><span>Entity profiles</span><strong>{number(entities.length)}</strong><small>Players, teams & statistical profiles <ArrowUpRight size={13} /></small></button><button onClick={() => setView("research")}><FlaskConical size={18} /><span>Research records</span><strong>{number(records.length)}</strong><small>Original verdicts, full evidence <ArrowUpRight size={13} /></small></button><button onClick={() => setView("library")}><Layers3 size={18} /><span>Published source modules</span><strong>{data.modules.length}</strong><small>Published modules across all sports <ArrowUpRight size={13} /></small></button><div><Database size={18} /><span>Snapshot checks</span><strong>{data.checks ? data.checks.pass : "--"}<em>/{data.checks ? data.checks.total : "--"}</em></strong><small>Recorded in the July manifest</small></div></div>
    <nav className="cv-view-nav" aria-label="Analytics workspace views">{views.map(({ id, label, Icon }) => <button key={id} aria-pressed={view === id} onClick={() => setView(id)}><Icon size={16} />{label}</button>)}</nav>
    <div className="cv-view" key={view}>
      {view === "overview" && sport === "nba" && <div className="cv-benchmarks"><WalkForward data={data.walkForward} /></div>}
      {(view === "overview" || view === "quality") && <Quality data={data} sport={sport} />}
      {view === "quality" && <Benchmarks data={data} sport={sport} />}
      {view === "overview" && <><div className="cv-overview-bottom"><Panel title="What survives testing?" eyebrow="Research outcomes" source="mechanism_ledger_export"><div className="cv-legend"><span><i className="cv-dot cv-confirmed" />Confirmed group</span><span><i className="cv-dot cv-null" />Null / other</span><span><i className="cv-dot cv-not_testable" />Not testable</span></div><div className="cv-verdict-chart">{SPORTS.filter(s => s.id !== "all" && (sport === "all" || s.id === sport)).map(s => { const rs = data.mechanisms.filter(r => r.sport === s.id); return <div key={s.id}><div className="cv-chart-label"><strong>{s.label}</strong><span>{rs.length} records</span></div><div className="cv-stacked" role="img" aria-label={`${s.label}: ${["confirmed", "null", "not_testable"].map(b => `${rs.filter(r => r.bucket === b).length} ${b}`).join(", ")}`}>{["confirmed", "null", "not_testable"].map(b => { const n = rs.filter(r => r.bucket === b).length; return <span key={b} className={`cv-${b}`} style={{ width: `${n / rs.length * 100}%` }}>{n}</span>; })}</div></div>; })}</div><button className="cv-text-button" onClick={() => setView("research")}>Inspect every research record <ArrowRight size={15} /></button><p className="cv-footnote">Grouped as recorded in the ledger. Local confirmation is not proof of causality. Open records to distinguish provisional and null findings.</p></Panel><Panel title="Choose your next question" eyebrow="Guided exploration" className="cv-discover"><a href={`${base}/analytics/novel/`}><span>01</span><div><h3>What can traditional stats miss?</h3><p>Six experimental lenses on lineups, fatigue, forecasts, and dependence.</p></div><ArrowUpRight size={19} /></a><a href={`${base}/analytics/findings/`}><span>02</span><div><h3>Which findings are worth reading?</h3><p>Measured results with their limitations and supporting evidence.</p></div><ArrowUpRight size={19} /></a><a href={`${base}/analytics/compare/`}><span>03</span><div><h3>How does a player compare?</h3><p>Statistical profiles and available percentile comparisons.</p></div><ArrowUpRight size={19} /></a><a href={`${base}/analytics/the-loop/`}><span>04</span><div><h3>How is the research checked?</h3><p>Follow the testing loop and its recorded outcomes.</p></div><ArrowUpRight size={19} /></a></Panel></div><Coverage data={data} sport={sport} /></>}
      {view === "research" && <Research rows={data.mechanisms} sport={sport} />}
      {view === "entities" && <Entities entities={data.entities} sport={sport} />}
      {view === "coverage" && <Coverage data={data} sport={sport} />}
      {view === "library" && <Catalog modules={data.modules} />}
    </div><div className="cv-bottom-note"><Database size={16} /><p>This workspace reads published snapshots. Dates and populations vary by source. Snapshot checks describe recorded results, not current system health.</p><a href={`${base}/analytics/about/`}>Methodology <ArrowUpRight size={14} /></a></div>
  </div></div>;
}
