import type { DossierCoverage } from "./dashboardTypes";

export type DossierCompletenessArtifact = {
  dossiers_count: number;
  categories_total: number;
  median_completeness_score: number;
  category_fill_rate: Record<string, number>;
  categories_filled_distribution: Record<string, number>;
};

export function buildDossierHistogram(distribution: Record<string, number>, denominator: number): DossierCoverage["histogram"] {
  return Object.entries(distribution)
    .map(([categoriesFilled, dossiers]) => ({ categoriesFilled: Number(categoriesFilled), dossiers, share: Number((dossiers / denominator).toFixed(6)) }))
    .sort((left, right) => left.categoriesFilled - right.categoriesFilled);
}

export function medianCategoriesFilled(histogram: DossierCoverage["histogram"]): number {
  const total = histogram.reduce((sum, bin) => sum + bin.dossiers, 0);
  const valueAt = (rank: number) => {
    let cumulative = 0;
    for (const bin of histogram) {
      cumulative += bin.dossiers;
      if (cumulative >= rank) return bin.categoriesFilled;
    }
    throw new Error("Histogram contains no value for the requested rank");
  };
  if (!total) throw new Error("Cannot find a median from an empty histogram");
  return total % 2 ? valueAt((total + 1) / 2) : (valueAt(total / 2) + valueAt(total / 2 + 1)) / 2;
}

export function buildDossierCoverage(artifact: DossierCompletenessArtifact): DossierCoverage {
  const histogram = buildDossierHistogram(artifact.categories_filled_distribution, artifact.dossiers_count);
  const medianCategories = medianCategoriesFilled(histogram);
  return {
    n: artifact.dossiers_count,
    median: artifact.median_completeness_score,
    categoriesTotal: artifact.categories_total,
    histogram,
    medianCategories,
    medianCategoriesShare: Number((medianCategories / artifact.categories_total).toFixed(6)),
    publishedCompletenessScore: artifact.median_completeness_score,
    rates: Object.entries(artifact.category_fill_rate).map(([name, value]) => ({ name, value })).sort((left, right) => right.value - left.value),
  };
}
