import { moduleCategory } from "./dashboardData";
import { analysisDestinations } from "./analysisDestinations";
import { findingsIndex } from "./findingsIndex";
import { snapshot } from "./labHelpers";
import { getResearchAnalyses } from "./researchData";
import type { ResearchAnalysis } from "./researchTypes";
import type { Sport } from "./dashboardTypes";
import type { LibraryEntry } from "./libraryTypes";
import { summarizeLibrarySource } from "./librarySourceSummaries";
import { loadPapers } from "./papers.server";
import { noticesForModules } from "./dataIntegrity";
import { moduleIdsForCitations } from "./sourceIntegrity.server";
import { readFileSync } from "node:fs";
import { join } from "node:path";

type Explainer = { slug: string; title: string; dek: string; cited: string[]; as_of?: string; sport?: Sport };
const kindLabel = {
  source: "Source module", derived: "Derived analysis", finding: "Finding", inspector: "Inspector", explainer: "Explainer", paper: "Paper",
} as const;

function explainers(): Explainer[] {
  const file = join(process.cwd(), "public", "data", "explainers", "explainers.json");
  return (JSON.parse(readFileSync(file, "utf8")) as { essays?: Explainer[] }).essays || [];
}

const SOURCE_SPORT: Record<string, Exclude<Sport, "all">> = {
  aging_curve_lite: "nba",
  box_value_index: "nba",
  cf_pace_variance: "nba",
  cf_star_removal: "nba",
  clutch_context: "nba",
  comeback_atlas: "nba",
  ctx_lineup_proxy: "nba",
  ctx_player_splits: "nba",
  ctx_team_states: "nba",
  home_away_anatomy: "nba",
  league_parity_index: "nba",
  lineup_synergy: "nba",
  novel_load_bearing_index: "nba",
  novel_schedule_fatigue_tax: "nba",
  on_off_showcase: "nba",
  player_metric_landscape: "nba",
  rim_deterrence: "nba",
  schedule_density: "nba",
  novel_pitch_repeat_excess: "mlb",
  pitch_sequencing: "mlb",
  statcast_showcase: "mlb",
};

function sourceSport(id: string): Sport {
  const prefix = /^(nba|mlb|soccer|tennis)_/.exec(id)?.[1] as Sport | undefined;
  return prefix || SOURCE_SPORT[id] || "all";
}

function sourceDescription(oneLine: string): string {
  const value = oneLine.trim();
  return value && !/^[A-Z][A-Z0-9_ -]*$/.test(value)
    ? value
    : "Explore the published chart, method, and evidence for this module.";
}

export function derivedAsOf(analysis: Pick<ResearchAnalysis, "asOf" | "sources">): string | null {
  return analysis.asOf || analysis.sources?.[0]?.asOf || null;
}

function integrityNotice(moduleIds: readonly string[]): string | undefined {
  const notices = noticesForModules(moduleIds);
  if (!notices.length) return undefined;
  return notices.some(notice => notice.status === "under-review")
    ? "Source integrity: under review (a stale input awaits recomposition)."
    : "Source integrity: revision 2 on the segment-clean corpus; revision 1 values withdrawn.";
}

export function getLibraryEntries(): LibraryEntry[] {
  const derived: LibraryEntry[] = getResearchAnalyses().map(a => ({
    id: a.id, title: a.title, description: a.description, category: a.category,
    sport: a.sport, kind: "derived", kindLabel: kindLabel.derived, status: a.status, href: `/analytics/research/${a.id}/`,
    asOf: derivedAsOf(a), keywords: `${a.source} ${a.formula} ${a.scope} ${a.fields.map(f => f.label).join(" ")}`,
    rows: a.rows.length, fields: a.fields.length,
    integrityNotice: integrityNotice([a.source, ...(a.sources || []).map(source => source.id)]),
    preview: a.rows.map(r => r.values[a.fields[0].key]).filter((v): v is number => typeof v === "number" && Number.isFinite(v)).slice(0, 16),
    previewLabel: a.fields[0].label,
  }));
  const manifest = snapshot<{ modules: { id: string; title: string; one_line: string; status: string; as_of: string | null }[] }>("site_manifest");
  const sources: LibraryEntry[] = manifest.modules.map(m => {
    const sourceSummary = summarizeLibrarySource(m.id, snapshot<Record<string, unknown>>(m.id), m.status);
    return ({
    id: m.id, title: m.title, description: sourceDescription(m.one_line),
    category: moduleCategory(m.id), sport: sourceSport(m.id),
    kind: "source", kindLabel: kindLabel.source, status: m.status, href: `/analytics/m/${m.id}/`, asOf: m.as_of || sourceSummary.asOf,
    keywords: m.id.replace(/_/g, " "), rows: null, fields: null, preview: [], previewLabel: "", sourceSummary,
    integrityNotice: integrityNotice([m.id]),
    });
  });
  const findings: LibraryEntry[] = findingsIndex.map(finding => ({
    id: finding.slug, title: finding.title, description: finding.dek, category: "Findings", sport: finding.sport,
    kind: "finding", kindLabel: kindLabel.finding, status: "published", href: `/analytics/findings/${finding.slug}/`, asOf: finding.asOf,
    keywords: finding.artifactIds.join(" "), rows: null, fields: null, preview: [], previewLabel: "",
    integrityNotice: integrityNotice(finding.artifactIds),
  }));
  const inspectors: LibraryEntry[] = analysisDestinations.map(destination => ({
    id: destination.id, title: destination.title, description: destination.purpose, category: "Inspectors", sport: destination.sport,
    kind: "inspector", kindLabel: kindLabel.inspector, status: "published", href: destination.route, asOf: null,
    keywords: `${destination.prerequisite} ${destination.nextQuestion}`, rows: null, fields: null, preview: [], previewLabel: "",
    integrityNotice: integrityNotice(destination.sourceModuleIds),
  }));
  const explainerEntries: LibraryEntry[] = explainers().map(essay => ({
    id: essay.slug, title: essay.title, description: essay.dek, category: "Explainers", sport: essay.sport || "all",
    kind: "explainer", kindLabel: kindLabel.explainer, status: "published", href: `/analytics/explainers/${essay.slug}/`, asOf: essay.as_of || null,
    keywords: essay.slug.replace(/-/g, " "), rows: null, fields: null, preview: [], previewLabel: "",
    integrityNotice: integrityNotice(moduleIdsForCitations(essay.cited)),
  }));
  const paperEntries: LibraryEntry[] = loadPapers().map(paper => ({
    id: paper.slug, title: paper.title, description: paper.subtitle, category: "Papers",
    sport: paper.sport === "soccer_intl" ? "soccer" : paper.sport,
    kind: "paper", kindLabel: kindLabel.paper, status: "published", href: `/analytics/papers/${paper.slug}/`, asOf: paper.date,
    keywords: paper.keywords.join(" "), rows: null, fields: null, preview: [], previewLabel: "",
    integrityNotice: integrityNotice(paper.evidence.map(evidence => evidence.module)),
  }));
  return [...derived, ...sources, ...findings, ...inspectors, ...explainerEntries, ...paperEntries];
}
