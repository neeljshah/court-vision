import type { ComparisonEntity, ComparisonPackKey } from "./comparisonData";

const PREFERRED_SLUGS: Partial<Record<ComparisonPackKey, string[]>> = {
  nba_players: ["nikola_jokic", "giannis_antetokounmpo", "shai_gilgeous_alexander", "luka_doncic"],
  nba_teams: ["bos", "den", "okc", "nyk"],
  mlb_batters: ["aaron_judge", "shohei_ohtani", "juan_soto"],
  mlb_pitch: ["ff", "sl", "si", "ch"],
  soccer: ["arsenal", "barcelona", "bayern_munich", "real_madrid"],
  tennis: ["jannik_sinner_atp", "carlos_alcaraz_atp", "taylor_fritz_atp"],
  calibration: ["mlb_band_0_2", "mlb_band_2_4"],
};

export function nonNullMeasurementCount(entity: ComparisonEntity): number {
  return Object.values(entity.values).filter((value) => value !== null && value !== undefined).length;
}

export function marqueePair(pack: ComparisonPackKey, entities: ComparisonEntity[]): [string, string] | undefined {
  if (entities.length < 2) return undefined;
  const preference = new Map((PREFERRED_SLUGS[pack] || []).map((slug, index) => [slug, index]));
  const ordered = [...entities].sort((left, right) => {
    const fieldDifference = nonNullMeasurementCount(right) - nonNullMeasurementCount(left);
    if (fieldDifference) return fieldDifference;
    const preferenceDifference = (preference.get(left.slug) ?? Infinity) - (preference.get(right.slug) ?? Infinity);
    return preferenceDifference || left.slug.localeCompare(right.slug);
  });
  return [ordered[0].slug, ordered[1].slug];
}
