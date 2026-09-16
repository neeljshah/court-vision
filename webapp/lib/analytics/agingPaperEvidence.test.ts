// Guards the aging paper against aging_curve_lite.json and player_metric_landscape.json. The
// paper's job is a refusal, so the test checks the refusal fields are reported verbatim, that the
// inflated claims the review rejected are gone, and that the shortened paper still validates.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
// @ts-expect-error -- the executable scanner is deliberately dependency-free ESM.
import { scanRenderedText } from "../../scripts/check-analytics-copy.mjs";
import { publishedArtifacts } from "./papers.server";
import { paperStrings, paperWordCount, validatePaper, type Paper } from "./papers";

function readJson(folder: string, name: string): any {
  return JSON.parse(readFileSync(join(process.cwd(), "public", "data", folder, `${name}.json`), "utf8"));
}

const AGING = readJson("papers", "age-and-production-lightly") as Paper;
const text = paperStrings(AGING).join(" ");
const curve = readJson("showcase", "aging_curve_lite");
const landscape = readJson("showcase", "player_metric_landscape");

describe("age-and-production-lightly", () => {
  it("reports the refusal fields the artifacts record", () => {
    expect(curve.status).toBe("not_buildable");
    expect(curve.age_source_found).toBeNull();
    expect(curve.n_seasons).toBe(3);
    expect(curve.seasons_available).toEqual(["2023-24", "2024-25", "2025-26"]);
    expect(landscape.coverage.rows).toBe(77744);
    expect(landscape.coverage.unique_players).toBe(807);
    expect(landscape.coverage.unique_games).toBe(3611);
    expect(landscape.coverage.seasons).toEqual(curve.seasons_available);
    expect(landscape.metric_families.aging_curve.verdict).toBe("not_supported");

    expect(text).toContain("status is not_buildable");
    expect(text).toContain("age_source_found is null");
    expect(text).toContain("n_seasons is 3");
    expect(text).toContain("77,744 player-game rows");
    expect(text).toContain("807 unique players");
    expect(text).toContain("3,611 unique games");
    expect(text).toContain("not_supported");
  });

  it("states the refusal plainly and keeps it", () => {
    expect(text).toContain("No age source was found, so no age curve was computed");
    expect(text).not.toMatch(/The honest result is a refusal/i);
    expect(text).not.toMatch(/peak-age estimate is reported here[^.]*computed/i);
  });

  it("drops the claims the review rejected", () => {
    // A few-season corpus does not "only ever" support a cross-sectional profile.
    expect(text).not.toMatch(/could ever support/i);
    // The scan reads readable top-level parquet files; it is not an exhaustive semantic audit.
    expect(text).toContain("top-level parquet files");
    expect(text).not.toMatch(/scanned all parquets/i);
    expect(text).not.toMatch(/reads every parquet table under/i);
    // No height/weight age substitute, and no independent-corroboration inflation.
    expect(text).not.toMatch(/height/i);
    expect(text).not.toMatch(/weight/i);
    expect(text).not.toMatch(/independently coded/i);
    expect(text).toContain("not independent corroboration");
  });

  it("is shortened, still valid, and free of prohibited vocabulary", () => {
    // papers.ts's validatePaper enforces no word bound of its own, so the band is asserted here.
    expect(validatePaper(AGING, publishedArtifacts())).toBeNull();
    const count = paperWordCount(AGING);
    expect(count).toBeGreaterThanOrEqual(900);
    expect(count).toBeLessThanOrEqual(1300);
    expect(scanRenderedText(text)).toEqual([]);
  });
});
