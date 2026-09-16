import { field as f, snapshot } from "./labHelpers";
import type { ResearchAnalysis, ResearchReference, ResearchRow } from "./researchTypes";

type Bucket = { n?: unknown; mean_abs_move?: unknown };
type Sport = { status?: unknown; n_series_used?: unknown; move_by_bucket?: unknown };
export type MicroAbsorptionSource = { as_of?: unknown; sports?: unknown; buckets_minutes?: unknown };

const REFERENCES: ResearchReference[] = [{
  title: "Published time-to-close movement method",
  url: "https://github.com/neeljshah/court-vision/blob/master/scripts/platformkit/analytics_showcase/micro_absorption.py",
}];
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const sportLabel = (sport: string) => sport === "soccer_intl" ? "International soccer" : sport.toUpperCase();
const asOf = (value: unknown) => typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : undefined;

function rows(source: MicroAbsorptionSource): ResearchRow[] {
  if (!source.sports || typeof source.sports !== "object" || Array.isArray(source.sports) || !Array.isArray(source.buckets_minutes)) return [];
  const buckets = source.buckets_minutes.flatMap((bucket, index) => typeof bucket === "object" && bucket && typeof (bucket as { label?: unknown }).label === "string" ? [{ label: (bucket as { label: string }).label, index }] : []);
  return Object.entries(source.sports as Record<string, unknown>).flatMap(([sport, value]) => {
    const entry = value as Sport;
    const seriesUsed = entry.n_series_used;
    if (entry.status !== "ok" || !finite(seriesUsed) || seriesUsed < 0 || !entry.move_by_bucket || typeof entry.move_by_bucket !== "object" || Array.isArray(entry.move_by_bucket)) return [];
    return buckets.flatMap(({ label, index }) => {
      const bucket = (entry.move_by_bucket as Record<string, unknown>)[label] as Bucket;
      if (!bucket || !finite(bucket.n) || bucket.n < 0 || !finite(bucket.mean_abs_move) || bucket.mean_abs_move < 0) return [];
      return [{
        id: `time-to-close-${sport}-${index}`,
        label: `${sportLabel(sport)} | ${label}`,
        group: sportLabel(sport),
        values: { mean_absolute_devigged_probability_movement: bucket.mean_abs_move, move_pairs: bucket.n, series_used: seriesUsed },
        note: `${bucket.n} published consecutive-snapshot move pairs across ${seriesUsed} series.`,
        sourcePaths: [`sports.${sport}.move_by_bucket.${label}.mean_abs_move`, `sports.${sport}.move_by_bucket.${label}.n`, `sports.${sport}.n_series_used`],
      }];
    });
  }).sort((left, right) => left.group.localeCompare(right.group) || left.label.localeCompare(right.label));
}

export function buildMicroAbsorptionResearch(source: MicroAbsorptionSource): ResearchAnalysis[] {
  const analysisRows = rows(source || {});
  return [{
    id: "devigged-movement-by-time-to-close",
    title: "Devigged probability movement by time to close",
    sport: "all",
    category: "Market measurement",
    source: "micro_absorption",
    question: "How much did published devigged probability move between consecutive snapshots in each time-to-close bucket?",
    method: "Restate each valid sport and minutes-to-close bucket with its mean absolute devigged probability movement, move-pair count, and series count.",
    description: "Published pre-event snapshot comparisons retain mean absolute movement and the underlying move-pair support.",
    scope: `${analysisRows.length} published valid sport-time buckets from the source observation window.`,
    caveat: "This is a short, source-specific capture window. Dense snapshots increase move-pair counts without creating independent events, and unavailable buckets remain omitted rather than imputed.",
    status: "Descriptive market-measurement subset",
    fields: [f("mean_absolute_devigged_probability_movement", "Mean absolute devigged probability movement", "percent", 4), f("move_pairs", "Move pairs", "number", 0), f("series_used", "Series used", "number", 0)],
    rows: analysisRows,
    formula: "Mean absolute devigged probability movement is copied from the published mean_abs_move field. Move pairs is copied from the published n field.",
    interpretation: "Compare the published mean absolute devigged probability movement with move pairs within the same sport and time-to-close bucket. The artifact records movement timing and does not identify its cause.",
    references: REFERENCES,
    novelty: "Derived analysis",
    asOf: asOf(source?.as_of),
  }];
}

export function getMicroAbsorptionResearch(): ResearchAnalysis[] {
  return buildMicroAbsorptionResearch(snapshot<MicroAbsorptionSource>("micro_absorption"));
}
