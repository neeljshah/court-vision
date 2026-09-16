import siteManifest from "../../public/data/showcase/site_manifest.json";

export type ResearchSourceDestination = {
  kind: "module" | "atlas" | "json";
  href: string;
};

const MODULE_IDS = new Set(siteManifest.modules.map(item => item.id));

// Atlas files publish entity packs rather than module pages. Keep the small
// route map here instead of importing the large card manifests into client code.
const ATLAS_PACKS: Record<string, string> = {
  atlas_calibration_manifest: "calibration",
  atlas_mlb_batters_manifest: "mlb_batters",
  atlas_mlb_pitch_manifest: "mlb_pitch",
  atlas_nba_manifest: "nba",
  atlas_nba_teams_manifest: "nba_teams",
  atlas_soccer_manifest: "soccer",
  atlas_tennis_manifest: "tennis",
};

export function resolveResearchSourceDestination(id: string): ResearchSourceDestination {
  if (MODULE_IDS.has(id)) return { kind: "module", href: `/analytics/m/${id}` };
  const pack = ATLAS_PACKS[id];
  if (pack) return { kind: "atlas", href: `/analytics/players#${pack}` };
  return { kind: "json", href: `/data/showcase/${id}.json` };
}
