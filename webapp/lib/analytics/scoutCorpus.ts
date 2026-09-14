// Build-time expansion of Ask Scout from committed public manifests.
// This reads required sources strictly: malformed or missing public data must fail a build.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { AskEntry } from "./askSearch";
import { getResearchAnalyses } from "./researchData";

type RawEntry = { entity: string; key_numbers: Record<string, unknown>; as_of: string | null };
type Manifest = { entries: RawEntry[] };
type Metric = { key: string; label: string; unit: string; scale?: number };
type Pack = { file: string; sport: string; kind: string; metrics: Metric[] };

const ROOT = join(process.cwd(), "public", "data");
const PACKS: Pack[] = [
  { file: "atlas_nba_manifest", sport: "nba", kind: "player", metrics: [
    { key: "career_pts_per36", label: "points", unit: "per 36 minutes" },
    { key: "career_ast_per36", label: "assists", unit: "per 36 minutes" },
    { key: "career_games", label: "games", unit: "games" },
  ] },
  { file: "atlas_nba_teams_manifest", sport: "nba", kind: "team", metrics: [
    { key: "ppg_latest_season", label: "points", unit: "per game, latest recorded season" },
    { key: "pace_proxy_latest_season", label: "pace proxy", unit: "proxy units, latest recorded season" },
  ] },
  { file: "atlas_mlb_batters_manifest", sport: "mlb", kind: "batter", metrics: [
    { key: "avg_exit_velo", label: "average exit velocity", unit: "mph" },
    { key: "pitches_faced", label: "pitches faced", unit: "pitches" },
  ] },
  { file: "atlas_mlb_pitch_manifest", sport: "mlb", kind: "pitch type", metrics: [
    { key: "velo_p50", label: "median velocity", unit: "mph" },
    { key: "top_pitch_type_pct", label: "top pitch-type share", unit: "%" },
    { key: "n_pitches", label: "recorded pitches", unit: "pitches" },
  ] },
  { file: "atlas_soccer_manifest", sport: "soccer", kind: "team", metrics: [
    { key: "ppg_l10", label: "points", unit: "per game, trailing 10" },
    { key: "gd_l10", label: "goal difference", unit: "per game, trailing 10" },
  ] },
  { file: "atlas_tennis_manifest", sport: "tennis", kind: "player", metrics: [
    { key: "hard_wr_career", label: "hard-court win rate (corpus)", unit: "%", scale: 100 },
    { key: "clay_wr_career", label: "clay-court win rate (corpus)", unit: "%", scale: 100 },
  ] },
  { file: "atlas_calibration_manifest", sport: "calibration", kind: "checkpoint", metrics: [
    { key: "model_ece", label: "model expected calibration error", unit: "unitless" },
    { key: "market_ece", label: "market expected calibration error", unit: "unitless" },
  ] },
];

function readRequired<T>(relative: string): T {
  const parsed: unknown = JSON.parse(readFileSync(join(ROOT, relative), "utf8"));
  if (!parsed || typeof parsed !== "object") throw new Error(`Invalid Scout source: ${relative}`);
  return parsed as T;
}

function entriesFrom(relative: string): RawEntry[] {
  const manifest = readRequired<Manifest>(relative);
  if (!Array.isArray(manifest.entries)) throw new Error(`Missing entries in Scout source: ${relative}`);
  return manifest.entries.map((entry, index) => {
    if (!entry || typeof entry.entity !== "string" || !entry.entity || !entry.key_numbers) {
      throw new Error(`Malformed Scout entry ${index} in ${relative}`);
    }
    return entry;
  });
}

function cleanName(name: string): string {
  return name.replace(/^pitch_type:/i, "pitch type ").replace(/_/g, " ").replace(/\s+/g, " ").trim();
}

function words(name: string): string[] {
  return cleanName(name).toLowerCase().replace(/[^a-z0-9\s]/g, " ").split(/\s+/).filter(Boolean);
}

function format(value: number, metric: Metric): string {
  const scaled = value * (metric.scale || 1);
  const precision = Number.isInteger(scaled) ? 0 : scaled < 1 ? 4 : 1;
  return `${scaled.toFixed(precision)} ${metric.unit}`;
}

function entityEntry(pack: Pack, entry: RawEntry, aliases: Set<string>): AskEntry {
  const name = cleanName(entry.entity);
  const values = pack.metrics.flatMap((metric) => {
    const value = entry.key_numbers[metric.key];
    return typeof value === "number" && Number.isFinite(value) ? [`${metric.label}: ${format(value, metric)}`] : [];
  });
  const source = `webapp/public/data/showcase/${pack.file}.json`;
  const asOf = entry.as_of || "date unrecorded";
  const surname = words(name).at(-1) || "";
  const alternates = [`${name} profile`, `Tell me about ${name}`];
  if (surname.length >= 4 && aliases.has(surname)) {
    alternates.push(surname, `${surname} profile`, `Tell me about ${surname}`);
  }
  return {
    q: `What public metrics are available for ${name}?`,
    alt_phrasings: alternates,
    tags: [pack.sport, pack.kind, "public-profile", ...words(name)],
    bucket: "public-entity-profile",
    a: {
      status: "ok",
      answer: values.length
        ? `Public ${pack.sport} ${pack.kind} profile for ${name}. As of ${asOf}: ${values.join("; ")}. This is a descriptive committed snapshot, not a current projection or live feed.`
        : `Public ${pack.sport} ${pack.kind} profile for ${name}. As of ${asOf}, the manifest has no configured numeric metrics for this profile. This is a descriptive committed snapshot, not a current projection or live feed.`,
      source_artifact: source,
      as_of: entry.as_of || "unknown",
    },
  };
}

function entityEntries(): AskEntry[] {
  const records = PACKS.flatMap((pack) => entriesFrom(`showcase/${pack.file}.json`).map((entry) => ({ pack, entry })));
  const counts = new Map<string, number>();
  records.forEach(({ entry }) => {
    const surname = words(entry.entity).at(-1);
    if (surname && surname.length >= 4) counts.set(surname, (counts.get(surname) || 0) + 1);
  });
  const uniqueSurnames = new Set(Array.from(counts).filter(([, count]) => count === 1).map(([name]) => name));
  return records.map(({ pack, entry }) => entityEntry(pack, entry, uniqueSurnames));
}

function moduleEntries(): AskEntry[] {
  const manifest = readRequired<{ modules: { id: string; title: string; one_line: string; status: string; as_of: string | null }[] }>("showcase/site_manifest.json");
  if (!Array.isArray(manifest.modules)) throw new Error("Missing modules in Scout source: showcase/site_manifest.json");
  return manifest.modules.map((module, index) => {
    if (!module.id || !module.title || !module.status) throw new Error(`Malformed Scout module ${index}`);
    const note = module.one_line.trim() || "No one-line methodology note is recorded in the public manifest.";
    return {
      q: `What does the ${module.title} analytics module cover?`,
      alt_phrasings: [module.title, `${module.title} module`],
      tags: ["analytics-module", module.status, ...words(module.title), ...module.id.split("_")],
      bucket: "public-analytics-module",
      a: {
        status: "ok",
        answer: `Public analytics module: ${module.title}. Status: ${module.status}. As of ${module.as_of || "date unrecorded"}. ${note} This is a committed module artifact, not a live result.`,
        source_artifact: `webapp/public/data/showcase/${module.id}.json`,
        as_of: module.as_of || "unknown",
      },
    };
  });
}

export function loadScoutCorpus(): AskEntry[] {
  const curated = readRequired<{ entries: AskEntry[] }>("ask/corpus.json");
  if (!Array.isArray(curated.entries)) throw new Error("Missing entries in Scout source: ask/corpus.json");
  const research: AskEntry[] = getResearchAnalyses().map(a => ({
    q: `Explain the analysis: ${a.title}`,
    alt_phrasings: [a.title, `${a.title} formula`, a.id.replace(/-/g, " ")],
    tags: [a.sport, "derived-analysis", ...words(a.title)], bucket: "public-derived-analysis",
    a: { status: "ok", answer: `${a.description} Formula: ${a.formula} ${a.interpretation} Scope: ${a.scope} Limitations: ${a.caveat} This is derived from a published snapshot, not a live forecast.`, source_artifact: `webapp/public/data/showcase/${a.source}.json`, as_of: a.asOf || "unknown" },
  }));
  return [...curated.entries, ...entityEntries(), ...moduleEntries(), ...research];
}
