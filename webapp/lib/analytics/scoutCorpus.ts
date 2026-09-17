// Pure builders for Ask Scout's committed corpus. Filesystem loading is server-only.
import type { AskEntry } from "./askSearch";
import { entrySlugs } from "./comparisonData";
import { getResearchAnalyses } from "./researchData";
import { buildReadingRoomAnswers, type ExplainerEssay, type PaperRecord, type SourceArtifact } from "./scoutInspectorAnswers";

type RawEntry = { entity: string; card_path: string; key_numbers: Record<string, unknown>; as_of?: string | null };
type Manifest = { entries: RawEntry[] };
type Metric = { key: string; label: string; unit: string; scale?: number };
type Pack = { file: string; routePack: string; sport: string; kind: string; metrics: Metric[] };
type ModuleManifest = { modules: { id: string; title: string; one_line: string; status: string; as_of: string | null }[] };

export type ScoutSources = { curated: { entries: AskEntry[] }; manifests: Record<string, Manifest>; siteManifest: ModuleManifest; inspectorArtifacts: SourceArtifact[]; explainers: ExplainerEssay[]; papers: PaperRecord[] };

const PACKS: Pack[] = [
  { file: "atlas_nba_manifest", routePack: "nba_players", sport: "nba", kind: "player", metrics: [{ key: "career_pts_per36", label: "points", unit: "per 36 minutes" }, { key: "career_ast_per36", label: "assists", unit: "per 36 minutes" }, { key: "career_games", label: "games", unit: "games" }] },
  { file: "atlas_nba_teams_manifest", routePack: "nba_teams", sport: "nba", kind: "team", metrics: [{ key: "ppg_latest_season", label: "points", unit: "per game, latest recorded season" }, { key: "pace_proxy_latest_season", label: "pace proxy", unit: "proxy units, latest recorded season" }] },
  { file: "atlas_mlb_batters_manifest", routePack: "mlb_batters", sport: "mlb", kind: "batter", metrics: [{ key: "avg_exit_velo", label: "average exit velocity", unit: "mph" }, { key: "pitches_faced", label: "pitches faced", unit: "pitches" }] },
  { file: "atlas_mlb_pitch_manifest", routePack: "mlb_pitch", sport: "mlb", kind: "pitch type", metrics: [{ key: "velo_p50", label: "median velocity", unit: "mph" }, { key: "top_pitch_type_pct", label: "top pitch-type share", unit: "%" }, { key: "n_pitches", label: "recorded pitches", unit: "pitches" }] },
  { file: "atlas_soccer_manifest", routePack: "soccer", sport: "soccer", kind: "team", metrics: [{ key: "ppg_l10", label: "points", unit: "per game, trailing 10" }, { key: "gd_l10", label: "goal difference", unit: "per game, trailing 10" }] },
  { file: "atlas_tennis_manifest", routePack: "tennis", sport: "tennis", kind: "player", metrics: [{ key: "hard_wr_career", label: "hard-court win rate (corpus)", unit: "%", scale: 100 }, { key: "clay_wr_career", label: "clay-court win rate (corpus)", unit: "%", scale: 100 }] },
  { file: "atlas_calibration_manifest", routePack: "calibration", sport: "calibration", kind: "checkpoint", metrics: [{ key: "model_ece", label: "model expected calibration error", unit: "unitless" }, { key: "market_ece", label: "market expected calibration error", unit: "unitless" }] },
];

function cleanName(name: string): string { return name.replace(/^pitch_type:/i, "pitch type ").replace(/_/g, " ").replace(/\s+/g, " ").trim(); }
function words(name: string): string[] { return cleanName(name).toLowerCase().replace(/[^a-z0-9\s]/g, " ").split(/\s+/).filter(Boolean); }
function format(value: number, metric: Metric): string { const scaled = value * (metric.scale || 1); return `${scaled.toFixed(Number.isInteger(scaled) ? 0 : scaled < 1 ? 4 : 1)} ${metric.unit}`; }

function bandValues(entry: RawEntry): string[] {
  const fields = [["mean_y_overall", "overall observed outcome rate"], ["band_reference", "band reference"], ["n", "published support"], ["by_time_bucket", "time-bucket observations"]] as const;
  return fields.flatMap(([key, label]) => {
    const value = entry.key_numbers[key];
    if (key === "by_time_bucket" && Array.isArray(value)) return [`${label}: ${value.length} published buckets`];
    return typeof value === "number" && Number.isFinite(value) ? [`${label}: ${key === "n" ? value.toLocaleString("en-US") : value}`] : [];
  });
}

function entityEntry(pack: Pack, entry: RawEntry, slug: string, aliases: Set<string>): AskEntry {
  const name = cleanName(entry.entity);
  const standard = pack.metrics.flatMap(metric => { const value = entry.key_numbers[metric.key]; return typeof value === "number" && Number.isFinite(value) ? [`${metric.label}: ${format(value, metric)}`] : []; });
  const values = standard.length ? standard : pack.routePack === "calibration" ? bandValues(entry) : [];
  const surname = words(name).at(-1) || "";
  const alternates = [`${name} profile`, `Tell me about ${name}`];
  if (surname.length >= 4 && aliases.has(surname)) alternates.push(surname, `${surname} profile`, `Tell me about ${surname}`);
  return { q: `What public metrics are available for ${name}?`, alt_phrasings: alternates, tags: [pack.sport, pack.kind, "public-profile", ...words(name)], bucket: "public-entity-profile", entity: { name: entry.entity, pack: pack.routePack, slug }, a: { status: "ok", answer: values.length ? `Public ${pack.sport} ${pack.kind} profile for ${name}. As of ${entry.as_of || "date unrecorded"}: ${values.join("; ")}. This is a descriptive committed snapshot, not a current projection or live feed.` : `Public ${pack.sport} ${pack.kind} profile for ${name}. As of ${entry.as_of || "date unrecorded"}, the manifest has no configured numeric metrics for this profile. This is a descriptive committed snapshot, not a current projection or live feed.`, source_artifact: `webapp/public/data/showcase/${pack.file}.json`, as_of: entry.as_of || "unknown", explore_path: `/analytics/players/${pack.routePack}/${slug}` } };
}

function entityEntries(manifests: Record<string, Manifest>): AskEntry[] {
  const records = PACKS.flatMap(pack => entrySlugs((manifests[pack.file]?.entries || []).map(entry => ({ ...entry, as_of: entry.as_of || undefined }))).map(({ entry, slug }) => ({ pack, entry, slug })));
  const counts = new Map<string, number>();
  records.forEach(({ entry }) => { const surname = words(entry.entity).at(-1); if (surname && surname.length >= 4) counts.set(surname, (counts.get(surname) || 0) + 1); });
  const uniqueSurnames = new Set(Array.from(counts).filter(([, count]) => count === 1).map(([name]) => name));
  return records.map(({ pack, entry, slug }) => entityEntry(pack, entry, slug, uniqueSurnames));
}

function moduleEntries(manifest: ModuleManifest): AskEntry[] {
  return manifest.modules.map(record => ({ q: `What does the ${record.title} analytics module cover?`, alt_phrasings: [record.title, `${record.title} module`], tags: ["analytics-module", record.status, ...words(record.title), ...record.id.split("_")], bucket: "public-analytics-module", a: { status: "ok", answer: `Public analytics module: ${record.title}. Status: ${record.status}. As of ${record.as_of || "date unrecorded"}. ${record.one_line.trim() || "No one-line methodology note is recorded in the public manifest."} This is a committed module artifact, not a live result.`, source_artifact: `webapp/public/data/showcase/${record.id}.json`, as_of: record.as_of || "unknown", explore_path: `/analytics/m/${record.id}` } }));
}

export function buildScoutCorpus(sources: ScoutSources): AskEntry[] {
  if (!Array.isArray(sources.curated.entries)) throw new Error("Missing entries in Scout source: ask/corpus.json");
  const research = getResearchAnalyses().map(analysis => ({ q: `Explain the analysis: ${analysis.title}`, alt_phrasings: [analysis.title, `${analysis.title} formula`, analysis.id.replace(/-/g, " ")], tags: [analysis.sport, "derived-analysis", ...words(analysis.title)], bucket: "public-derived-analysis", a: { status: "ok" as const, answer: `${analysis.description} Formula: ${analysis.formula} ${analysis.interpretation} Scope: ${analysis.scope} Limitations: ${analysis.caveat} This is derived from a published snapshot, not a live forecast.`, source_artifact: `webapp/public/data/showcase/${analysis.source}.json`, source_module_ids: Array.from(new Set([analysis.source, ...(analysis.sources || []).map(source => source.id)])), as_of: analysis.asOf || "unknown", explore_path: `/analytics/research/${analysis.id}/` } }));
  return [...sources.curated.entries, ...buildReadingRoomAnswers(sources.inspectorArtifacts, sources.explainers, sources.papers), ...entityEntries(sources.manifests), ...moduleEntries(sources.siteManifest), ...research];
}

export function scoutCorpusExpectedCount(sources: ScoutSources): number { return sources.curated.entries.length + Object.values(sources.manifests).reduce((total, manifest) => total + manifest.entries.length, 0) + sources.siteManifest.modules.length + getResearchAnalyses().length + sources.inspectorArtifacts.length + sources.explainers.length + sources.papers.length; }
