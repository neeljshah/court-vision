import { atlasFieldDefinition, atlasPackFieldDefinitions, type AtlasFieldDefinition } from "./atlasFieldDefinitions";
import { getMlbPitchAtlasCohorts } from "./atlasResearchCohorts";
import { getEntityMeasurementSchema } from "./entityMeasurementSchemas";

export type EntityEntry = { entity?: string; card_type?: string; key_numbers: Record<string, unknown>; floors?: string };
export type EntityPercentilePack = { n_in_pack: number; fields: Record<string, { n_ranked: number }>; entities: Record<string, Record<string, number>> };
export type ScalarMeasurement = { key: string; label: string; value: string; unit?: string; percentile?: number; nRanked?: number; percentileUnavailable?: boolean };
export type Distribution = { key: string; label: string; rows: Array<{ key: string; share: number }> };
export type UnavailableMeasurement = { key: string; label: string; floor?: string };
export type MeasurementTable =
  | { key: "velo_percentiles_by_type"; label: string; rows: Array<{ type: string; n: number; p10: number; p50: number; p90: number }> }
  | { key: "by_time_bucket"; label: string; rows: Array<{ bucket: string; n: number; meanY: number }> };
export type EntityMeasurements = { scalars: ScalarMeasurement[]; distributions: Distribution[]; tables: MeasurementTable[]; unavailable: UnavailableMeasurement[]; notApplicable: UnavailableMeasurement[]; cohort: string };

export function measurementLabel(key: string): string { return atlasFieldDefinition("", key).label; }

function formatted(field: AtlasFieldDefinition, value: string | number | boolean): { value: string; unit?: string } {
  if (typeof value === "boolean") return { value: value ? "yes" : "no" };
  if (typeof value === "string") return { value };
  if (field.unit === "percent-already") return { value: `${value.toFixed(field.decimals)}%`, unit: "%" };
  if (field.unit === "fraction-as-percent") {
    const suffix = field.isDifference ? " pp" : "%";
    return { value: `${(value * 100).toFixed(field.decimals)}${suffix}`, unit: suffix.trim() };
  }
  if (field.unit === "mph") return { value: `${value.toFixed(field.decimals)} mph`, unit: "mph" };
  return { value: Number.isInteger(value) ? String(value) : String(Number(value.toFixed(field.decimals))) };
}

function floorFor(key: string, floors?: string): string | undefined {
  if (!floors) return undefined;
  const root = key.replace(/_(career|recent)$/, "");
  return floors.split("|").map((part) => part.trim()).find((part) => part.startsWith(`${root}:`));
}

function velocityRows(value: unknown): Array<{ type: string; n: number; p10: number; p50: number; p90: number }> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const rows = Object.entries(value).flatMap(([type, row]) => {
    if (!row || typeof row !== "object" || Array.isArray(row)) return [];
    const item = row as Record<string, unknown>;
    return ["n", "p10", "p50", "p90"].every((key) => typeof item[key] === "number")
      ? [{ type, n: item.n as number, p10: item.p10 as number, p50: item.p50 as number, p90: item.p90 as number }]
      : [];
  });
  return rows.length ? rows : null;
}

function timeBucketRows(value: unknown): Array<{ bucket: string; n: number; meanY: number }> | null {
  if (!Array.isArray(value)) return null;
  const rows = value.flatMap((row) => {
    if (!row || typeof row !== "object") return [];
    const item = row as Record<string, unknown>;
    return typeof item.bucket === "string" && typeof item.n === "number" && typeof item.mean_y === "number"
      ? [{ bucket: item.bucket, n: item.n, meanY: item.mean_y }]
      : [];
  });
  return rows.length ? rows : null;
}

function withinCohortPercentile(key: string, value: number, entry: EntityEntry, cohortEntries?: EntityEntry[]): Pick<ScalarMeasurement, "percentile" | "nRanked" | "percentileUnavailable"> {
  if (!cohortEntries || !entry.entity) return { percentileUnavailable: true };
  const cohort = getMlbPitchAtlasCohorts(cohortEntries as Parameters<typeof getMlbPitchAtlasCohorts>[0])
    .find((item) => item.entries.some((candidate) => candidate.entity === entry.entity));
  const values = cohort?.entries.map((candidate) => candidate.key_numbers[key]).filter((candidate): candidate is number => typeof candidate === "number" && Number.isFinite(candidate)) || [];
  if (values.length < 2) return { percentileUnavailable: true };
  const percentile = Number((100 * values.filter((candidate) => candidate <= value).length / values.length).toFixed(6));
  return { percentile, nRanked: values.length };
}

function percentileFor(pack: string, key: string, value: number, entry: EntityEntry, slug: string, percentilePack?: EntityPercentilePack | null, cohortEntries?: EntityEntry[]): Pick<ScalarMeasurement, "percentile" | "nRanked" | "percentileUnavailable"> {
  if (pack === "mlb_pitch") return withinCohortPercentile(key, value, entry, cohortEntries);
  const rank = percentilePack?.entities[slug]?.[key];
  return typeof rank === "number" ? { percentile: rank, nRanked: percentilePack?.fields[key]?.n_ranked } : {};
}

export function entityMeasurements(pack: string, entry: EntityEntry, slug: string, percentilePack?: EntityPercentilePack | null, cohortEntries?: EntityEntry[]): EntityMeasurements {
  const schema = getEntityMeasurementSchema(pack, entry);
  const known = atlasPackFieldDefinitions(pack);
  const byKey = new Map(known.map((field) => [field.key, field]));
  const expected = schema.fields.map((key) => byKey.get(key) || atlasFieldDefinition(pack, key));
  const extras = Object.keys(entry.key_numbers).filter((key) => !byKey.has(key)).sort().map((key) => atlasFieldDefinition(pack, key));
  const notApplicable = known.filter((field) => !field.isIdentifier && !schema.fields.includes(field.key)).map(({ key, label }) => ({ key, label }));
  const scalars: ScalarMeasurement[] = [];
  const distributions: Distribution[] = [];
  const tables: MeasurementTable[] = [];
  const unavailable: UnavailableMeasurement[] = [];
  for (const field of [...expected, ...extras]) {
    if (field.isIdentifier) continue;
    const { key, label } = field;
    const value = entry.key_numbers[key];
    if (value === null || value === undefined) { unavailable.push({ key, label, floor: floorFor(key, entry.floors) }); continue; }
    if (key === "velo_percentiles_by_type") { const rows = velocityRows(value); if (rows) tables.push({ key, label, rows }); else unavailable.push({ key, label, floor: floorFor(key, entry.floors) }); continue; }
    if (key === "by_time_bucket") { const rows = timeBucketRows(value); if (rows) tables.push({ key, label, rows }); else unavailable.push({ key, label, floor: floorFor(key, entry.floors) }); continue; }
    if (value && typeof value === "object" && /_pct$/.test(key)) {
      const rows = Object.entries(value).filter((row): row is [string, number] => typeof row[1] === "number").map(([rowKey, share]) => ({ key: rowKey, share }));
      if (rows.length) distributions.push({ key, label, rows }); else unavailable.push({ key, label, floor: floorFor(key, entry.floors) });
    } else if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
      scalars.push({ key, label, ...formatted(field, value), ...(typeof value === "number" ? percentileFor(pack, key, value, entry, slug, percentilePack, cohortEntries) : {}) });
    }
  }
  return { scalars, distributions, tables, unavailable, notApplicable, cohort: schema.cohort };
}
