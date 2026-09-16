import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { buildDossierCoverage, type DossierCompletenessArtifact } from "./dossierCoverage";

const artifact = JSON.parse(readFileSync(join(process.cwd(), "public/data/showcase/dossier_completeness.json"), "utf8")) as DossierCompletenessArtifact;
const coverage = buildDossierCoverage(artifact);

describe("dossier completeness coverage", () => {
  it("turns every published distribution entry into a share of the 1,249 audited dossiers", () => {
    expect(coverage.histogram.reduce((sum, bin) => sum + bin.dossiers, 0)).toBe(1249);
    expect(coverage.histogram.find(bin => bin.categoriesFilled === 18)).toEqual({ categoriesFilled: 18, dossiers: 82, share: 0.065653 });
  });

  it("derives the median filled categories from the published distribution", () => {
    expect(coverage.medianCategories).toBe(18);
    expect(coverage.medianCategoriesShare).toBe(0.642857);
  });

  it("carries the published completeness score through unchanged", () => {
    expect(coverage.publishedCompletenessScore).toBe(artifact.median_completeness_score);
    expect(coverage.median).toBe(artifact.median_completeness_score);
  });

  it("sorts category fill rates from most to least filled", () => {
    expect(coverage.rates).toEqual([...coverage.rates].sort((left, right) => right.value - left.value));
    expect(coverage.rates[0]).toEqual({ name: "rebounding_profile", value: 0.9544 });
  });
});
