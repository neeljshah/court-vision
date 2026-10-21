// Server-only: dynamic route families for app/sitemap.ts, read straight off the baked artifacts.
// In a snapshot build a missing, unreadable or empty artifact THROWS: an empty family would
// drop its routes from the sitemap with a green build. Live builds keep the empty fallback.
// /receipts/<i>: i is the row's position in public/receipts.json `rows`, the same array the
// receipt pages export from (app/(terminal)/receipts/[row]/page.tsx generateStaticParams).
// The rows carry no stable id; app/(terminal)/receipts/__tests__/receipts-ordering.test.ts
// documents that contract and fails the day an id appears.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { listClaimSlugs } from "@/lib/evidence.server";
import { isSnapshotMode } from "@/lib/fetchHonest";
import { paperDetailHref } from "@/lib/paperLinks";
import { bakedFillParams } from "@/components/paper_pm/bakedFillParams.server";

const real = (s: string) => !!s && s !== "none";

export type Families = { claims: string[]; fills: string[]; receipts: string[]; explainers: string[]; games: string[];
  fillsAsOf?: string; gamesAsOf?: string };

export function sitemapFamilies(snapshot = isSnapshotMode, publicDir = join(process.cwd(), "public")): Families {
  const read = (rel: string): any => {
    try { return JSON.parse(readFileSync(join(publicDir, rel), "utf-8")); } catch (e) {
      if (!snapshot) return null;
      const why = e instanceof Error ? e.message : String(e);
      throw new Error(`snapshot build: public/${rel} is missing or unreadable (${why}), so its sitemap family cannot be listed`);
    }
  };
  const rows = <T,>(rel: string, key: string, list: unknown): T[] => {
    const arr = Array.isArray(list) ? (list as T[]) : [];
    if (snapshot && !arr.length) throw new Error(`snapshot build: public/${rel} has no ${key}, so that sitemap family would be empty`);
    return arr;
  };
  const manifest = read("demo-data/manifest.json");
  const games = rows<{ sport: string; game_id: string }>("demo-data/manifest.json", "games", manifest?.games);
  rows<string>("demo-data/manifest.json", "bet_ids", manifest?.bet_ids); // the /paper/<id> export list (next.config.mjs)
  const receipts = rows<unknown>("receipts.json", "rows", read("receipts.json")?.rows);
  const essays = rows<{ slug: string }>("data/explainers/explainers.json", "essays", read("data/explainers/explainers.json")?.essays);
  return {
    claims: listClaimSlugs().filter(real).map((c) => `/evidence/${c}`),
    // The export directory is the once-encoded fill id; the public href carries one more layer (lib/paperLinks).
    fills: bakedFillParams(join(publicDir, "demo-data/api_paper_trail_limit_400.json"), snapshot)
      .filter(real).map((f) => paperDetailHref(f).replace(/\/$/, "")),
    receipts: receipts.map((_, i) => `/receipts/${i}`),
    explainers: essays.filter((e) => real(e.slug)).map((e) => `/analytics/explainers/${e.slug}`),
    games: games.filter((g) => real(g.sport) && real(g.game_id)).map((g) => `/games/${g.sport}/${g.game_id}`),
    fillsAsOf: read("demo-data/api_paper_trail_limit_400.json")?.as_of,
    gamesAsOf: manifest?.generated_at,
  };
}
