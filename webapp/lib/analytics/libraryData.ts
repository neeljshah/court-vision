import { moduleCategory } from "./dashboardData";
import { snapshot } from "./labHelpers";
import { getResearchAnalyses } from "./researchData";
import type { Sport } from "./dashboardTypes";
import type { LibraryEntry } from "./libraryTypes";
import { summarizeLibrarySource } from "./librarySourceSummaries";

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

export function getLibraryEntries(): LibraryEntry[] {
  const derived: LibraryEntry[] = getResearchAnalyses().map(a => ({
    id: a.id, title: a.title, description: a.description, category: a.category,
    sport: a.sport, kind: "derived", status: a.status, href: `/analytics/research/${a.id}/`,
    asOf: a.asOf || null, keywords: `${a.source} ${a.formula} ${a.scope} ${a.fields.map(f => f.label).join(" ")}`,
    rows: a.rows.length, fields: a.fields.length,
    preview: a.rows.map(r => r.values[a.fields[0].key]).filter((v): v is number => typeof v === "number" && Number.isFinite(v)).slice(0, 16),
    previewLabel: a.fields[0].label,
  }));
  const manifest = snapshot<{ modules: { id: string; title: string; one_line: string; status: string; as_of: string | null }[] }>("site_manifest");
  const sources: LibraryEntry[] = manifest.modules.map(m => {
    const sourceSummary = summarizeLibrarySource(m.id, snapshot<Record<string, unknown>>(m.id), m.status);
    return ({
    id: m.id, title: m.title, description: sourceDescription(m.one_line),
    category: moduleCategory(m.id), sport: sourceSport(m.id),
    kind: "source", status: m.status, href: `/analytics/m/${m.id}/`, asOf: m.as_of || sourceSummary.asOf,
    keywords: m.id.replace(/_/g, " "), rows: null, fields: null, preview: [], previewLabel: "", sourceSummary,
    });
  });
  return [...derived, ...sources];
}
