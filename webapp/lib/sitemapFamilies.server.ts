// Server-only: dynamic route families for app/sitemap.ts, read straight off the baked artifacts.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { listClaimSlugs } from "@/lib/evidence.server";
import { bakedFillParams } from "@/components/paper_pm/bakedFillParams.server";

const read = (rel: string): any => {
  try { return JSON.parse(readFileSync(join(process.cwd(), "public", rel), "utf-8")); } catch { return null; }
};
const real = (s: string) => !!s && s !== "none";

export type Families = { claims: string[]; fills: string[]; receipts: string[]; explainers: string[]; games: string[];
  fillsAsOf?: string; gamesAsOf?: string };

export function sitemapFamilies(): Families {
  const manifest = read("demo-data/manifest.json");
  return {
    claims: listClaimSlugs().filter(real).map((c) => `/evidence/${c}`),
    fills: bakedFillParams().filter(real).map((f) => `/paper/${f}`), // already URL-encoded; do NOT re-encode
    receipts: ((read("receipts.json")?.rows ?? []) as unknown[]).map((_, i) => `/receipts/${i}`),
    explainers: ((read("data/explainers/explainers.json")?.essays ?? []) as Array<{ slug: string }>)
      .filter((e) => real(e.slug)).map((e) => `/analytics/explainers/${e.slug}`),
    games: ((manifest?.games ?? []) as Array<{ sport: string; game_id: string }>)
      .filter((g) => real(g.sport) && real(g.game_id)).map((g) => `/games/${g.sport}/${g.game_id}`),
    fillsAsOf: read("demo-data/api_paper_trail_limit_400.json")?.as_of,
    gamesAsOf: manifest?.generated_at,
  };
}
