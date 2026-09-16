import { atlasFieldDefinition, atlasPackFieldDefinitions, type AtlasFieldDefinition } from "./atlasFieldDefinitions";

export type EntityEntry = { key_numbers: Record<string, unknown>; floors?: string };
export type EntityPercentilePack = {
  n_in_pack: number;
  fields: Record<string, { n_ranked: number }>;
  entities: Record<string, Record<string, number>>;
};
export type ScalarMeasurement = {
  key: string; label: string; value: string; unit?: string; percentile?: number; nRanked?: number;
};
export type Distribution = { key: string; label: string; rows: Array<{ key: string; share: number }> };
export type UnavailableMeasurement = { key: string; label: string; floor?: string };
export type EntityMeasurements = { scalars: ScalarMeasurement[]; distributions: Distribution[]; unavailable: UnavailableMeasurement[] };

export function measurementLabel(key: string): string {
  return atlasFieldDefinition("", key).label;
}

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

export function entityMeasurements(
  pack: string, entry: EntityEntry, slug: string, percentilePack?: EntityPercentilePack | null,
): EntityMeasurements {
  const known = atlasPackFieldDefinitions(pack);
  const unknown = Object.keys(entry.key_numbers).filter(key => !known.some(field => field.key === key)).sort().map(key => atlasFieldDefinition(pack, key));
  const expected = [...known, ...unknown];
  const ranks = percentilePack?.entities[slug] || {};
  const scalars: ScalarMeasurement[] = [];
  const distributions: Distribution[] = [];
  const unavailable: UnavailableMeasurement[] = [];
  for (const field of expected) {
    if (field.isIdentifier) continue;
    const { key, label } = field;
    const value = entry.key_numbers[key];
    if (value === null || value === undefined) {
      unavailable.push({ key, label, floor: floorFor(key, entry.floors) });
    } else if (value && typeof value === "object" && /_pct$/.test(key)) {
      const rows = Object.entries(value).filter((row): row is [string, number] => typeof row[1] === "number").map(([rowKey, share]) => ({ key: rowKey, share }));
      if (rows.length) distributions.push({ key, label, rows });
    } else if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
      const display = formatted(field, value);
      scalars.push({ key, label, ...display, percentile: ranks[key], nRanked: percentilePack?.fields[key]?.n_ranked });
    }
  }
  return { scalars, distributions, unavailable };
}
