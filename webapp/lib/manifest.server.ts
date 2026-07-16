// manifest.server.ts -- server-only reader for the snapshot-demo manifest
// written by scripts/platformkit/publish_demo/export_snapshot.py. Used only by
// generateStaticParams (build-time) so `next build --output export` knows
// which dynamic [sport]/[gameId]/[betId] pages to pre-render. Missing file
// (normal dev/live build, or before the exporter has ever run) -> empty lists,
// dynamicParams=true still lets live mode render any param on demand.

import { promises as fs } from "node:fs";
import path from "node:path";

export type DemoManifest = {
  generated_at: string;
  sports: string[];
  games: { sport: string; game_id: string }[];
  bet_ids: string[];
};

let cached: DemoManifest | null | undefined;

export async function readManifest(): Promise<DemoManifest | null> {
  if (cached !== undefined) return cached;
  try {
    const p = path.join(process.cwd(), "public", "demo-data", "manifest.json");
    const raw = await fs.readFile(p, "utf-8");
    cached = JSON.parse(raw) as DemoManifest;
  } catch {
    cached = null;
  }
  return cached;
}
