// Build-time loader for Scout's committed JSON. Keep node:fs out of client-reachable modules.
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { analysisDestinations } from "./analysisDestinations";
import { buildScoutCorpus, type ScoutSources } from "./scoutCorpus";

const root = () => join(process.cwd(), "public", "data");
const packs = ["atlas_nba_manifest", "atlas_nba_teams_manifest", "atlas_mlb_batters_manifest", "atlas_mlb_pitch_manifest", "atlas_soccer_manifest", "atlas_tennis_manifest", "atlas_calibration_manifest"];
function readRequired<T>(relative: string): T { const parsed: unknown = JSON.parse(readFileSync(join(root(), relative), "utf8")); if (!parsed || typeof parsed !== "object") throw new Error(`Invalid Scout source: ${relative}`); return parsed as T; }
function sources(): ScoutSources {
  const siteManifest = readRequired<ScoutSources["siteManifest"]>("showcase/site_manifest.json");
  const manifestById = new Map(siteManifest.modules.map(record => [record.id, record]));
  const inspectorArtifacts = analysisDestinations.flatMap(destination => destination.sourceModuleIds.map(id => { const manifest = manifestById.get(id); if (!manifest) throw new Error(`Missing Inspector source in site manifest: ${id}`); return { id, artifact: `webapp/public/data/showcase/${id}.json`, asOf: manifest.as_of, data: readRequired<unknown>(`showcase/${id}.json`) }; }));
  const papers = readdirSync(join(root(), "papers")).filter(file => file.endsWith(".json")).map(file => readRequired<ScoutSources["papers"][number]>(`papers/${file}`));
  return { curated: readRequired<ScoutSources["curated"]>("ask/corpus.json"), manifests: Object.fromEntries(packs.map(id => [id, readRequired<ScoutSources["manifests"][string]>(`showcase/${id}.json`)])), siteManifest, inspectorArtifacts, explainers: readRequired<{ essays: ScoutSources["explainers"] }>("explainers/explainers.json").essays, papers };
}
export function loadScoutCorpus() { return buildScoutCorpus(sources()); }
export function loadScoutSourcesForTest(): ScoutSources { return sources(); }
