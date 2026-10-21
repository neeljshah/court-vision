// sitemapFamilies.server.test.ts -- in a snapshot build a missing or empty baked
// artifact throws (an empty family would silently drop its routes from the sitemap);
// a live build keeps the empty fallback. bakedFillParams follows the same rule.
import { describe, expect, it } from "vitest";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { sitemapFamilies } from "../sitemapFamilies.server";
import { bakedFillParams } from "@/components/paper_pm/bakedFillParams.server";

const trailRow = {
  sport: "mlb", game_id: "G1", side: "home", market_type: "moneyline", taken_book: "kalshi", ts: "2026-10-08T00:00:00Z",
};

/** A public/ directory with only the named artifacts written. */
function publicDir(files: Record<string, unknown>): string {
  const dir = mkdtempSync(join(tmpdir(), "sitemap-public-"));
  for (const sub of ["demo-data", "data/explainers"]) mkdirSync(join(dir, sub), { recursive: true });
  for (const [rel, body] of Object.entries(files)) writeFileSync(join(dir, rel), JSON.stringify(body));
  return dir;
}

const complete = {
  "demo-data/manifest.json": { generated_at: "2026-07-16T01:45:31Z", games: [{ sport: "mlb", game_id: "G1" }], bet_ids: ["b1"] },
  "demo-data/api_paper_trail_limit_400.json": { as_of: "2026-10-09T06:00:00Z", trail: [trailRow] },
  "receipts.json": { rows: [{ sport_market: "mlb/total_runs" }, { sport_market: "mlb/moneyline" }] },
  "data/explainers/explainers.json": { essays: [{ slug: "why-brier" }, { slug: "none" }] },
};

describe("sitemapFamilies", () => {
  it("lists every family from a complete snapshot export", () => {
    const f = sitemapFamilies(true, publicDir(complete));
    expect(f.games).toEqual(["/games/mlb/G1"]);
    expect(f.receipts).toEqual(["/receipts/0", "/receipts/1"]);
    expect(f.explainers).toEqual(["/analytics/explainers/why-brier"]);
    expect(f.fills).toHaveLength(1);
    expect(f.fillsAsOf).toBe("2026-10-09T06:00:00Z");
    expect(f.gamesAsOf).toBe("2026-07-16T01:45:31Z");
    expect(f.claims.length).toBeGreaterThan(0);
  });

  it("throws in a snapshot build for each missing or empty artifact, naming it", () => {
    const without = (rel: string) => Object.fromEntries(Object.entries(complete).filter(([k]) => k !== rel));
    expect(() => sitemapFamilies(true, publicDir(without("demo-data/manifest.json"))))
      .toThrow(/public\/demo-data\/manifest\.json is missing or unreadable/);
    expect(() => sitemapFamilies(true, publicDir({ ...complete, "demo-data/manifest.json": { games: [], bet_ids: ["b1"] } })))
      .toThrow(/manifest\.json has no games/);
    expect(() => sitemapFamilies(true, publicDir({ ...complete, "demo-data/manifest.json": { games: [{ sport: "mlb", game_id: "G1" }] } })))
      .toThrow(/manifest\.json has no bet_ids/);
    expect(() => sitemapFamilies(true, publicDir(without("receipts.json")))).toThrow(/public\/receipts\.json is missing/);
    expect(() => sitemapFamilies(true, publicDir({ ...complete, "receipts.json": { rows: [] } }))).toThrow(/receipts\.json has no rows/);
    expect(() => sitemapFamilies(true, publicDir({ ...complete, "data/explainers/explainers.json": {} })))
      .toThrow(/explainers\.json has no essays/);
    expect(() => sitemapFamilies(true, publicDir(without("demo-data/api_paper_trail_limit_400.json"))))
      .toThrow(/api_paper_trail_limit_400\.json is missing or unreadable/);
    expect(() => sitemapFamilies(true, publicDir({ ...complete, "demo-data/api_paper_trail_limit_400.json": { trail: [] } })))
      .toThrow(/has no trail rows/);
  });

  it("keeps the empty fallback outside a snapshot build", () => {
    const f = sitemapFamilies(false, publicDir({}));
    expect([f.games, f.receipts, f.explainers, f.fills]).toEqual([[], [], [], []]);
    expect(f.fillsAsOf).toBeUndefined();
  });
});

describe("bakedFillParams", () => {
  it("throws in a snapshot build when the trail is missing or empty, and returns [] live", () => {
    const dir = publicDir({ "demo-data/empty.json": { trail: [] } });
    expect(() => bakedFillParams(join(dir, "demo-data/none.json"), true)).toThrow(/missing or unreadable/);
    expect(() => bakedFillParams(join(dir, "demo-data/empty.json"), true)).toThrow(/has no trail rows/);
    expect(bakedFillParams(join(dir, "demo-data/none.json"), false)).toEqual([]);
    expect(bakedFillParams().length).toBeGreaterThan(0);
  });
});
