import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { normalizeComparisonPack, type RawManifest, type RawPercentiles } from "./comparisonData";
import { tennisSurfaceComparison, type TennisSurface } from "./tennisSurfaceComparison";

const publicJson = (name: string) => JSON.parse(readFileSync(resolve(__dirname, "../../public/data/showcase", name), "utf8"));
const manifest: RawManifest = publicJson("atlas_tennis_manifest.json");
const percentiles: RawPercentiles = publicJson("entity_percentiles.json");
const pack = normalizeComparisonPack("tennis", manifest, percentiles, {});

describe("published tennis surface integration", () => {
  it("preserves each public field's independent availability and evidence", () => {
    expect(pack.entities.length).toBeGreaterThan(250);
    for (const [index, a] of pack.entities.entries()) {
      const source = manifest.entries![index];
      for (const surface of ["hard", "clay", "grass"] as TennisSurface[]) {
        const result = tennisSurfaceComparison(a, pack.entities[(index + 1) % pack.entities.length], surface);
        expect(result.entities.a).toMatchObject({ floors: source.floors, status: source.status, asOf: source.as_of });
        for (const row of result.rows) {
          const value = source.key_numbers[row.key];
          expect(row.a.value).toBe(typeof value === "number" && Number.isFinite(value) ? value : null);
          if (row.a.value === null) expect(row.a.percentile).toBeNull();
          else {
            expect(row.a.value).toBeGreaterThanOrEqual(row.kind === "surface_rate" ? 0 : -1);
            expect(row.a.value).toBeLessThanOrEqual(1);
          }
        }
      }
    }
  });

  it("retains Zverev's recent grass adaptation when his stricter grass rate is unavailable", () => {
    const a = pack.entities.find(entity => entity.slug === "alexander_zverev_atp")!;
    const b = pack.entities.find(entity => entity.slug === "ivo_karlovic_atp")!;
    expect(a).toBeDefined();
    expect(b).toBeDefined();
    const result = tennisSurfaceComparison(a, b, "grass");
    expect(result.rows.find(row => row.key === "grass_wr_recent")?.a.value).toBeNull();
    expect(result.rows.find(row => row.key === "grass_adapt_recent")?.a.value).toBe(-0.0054);
    expect(result.rows.filter(row => row.window === "recent").every(row => row.b.value === null)).toBe(true);
    expect(result.entities.a.floors).toContain("grass_wr: grass_n>=30");
    expect(result.entities.a.floors).toContain("grass_adapt: grass_n>=15");
  });

  it("exposes published recent grass rates even though the atlas has no percentile column for them", () => {
    expect(pack.metricKeys).not.toContain("grass_wr_recent");
    const measured = pack.entities.filter(entity => typeof entity.values.grass_wr_recent === "number");
    expect(measured).toHaveLength(3);
    for (const a of measured) {
      const row = tennisSurfaceComparison(a, pack.entities[0], "grass").rows.find(item => item.key === "grass_wr_recent");
      expect(row?.a.value).toBe(a.values.grass_wr_recent);
      expect(row?.a.percentile).toBeNull();
    }
  });
});
