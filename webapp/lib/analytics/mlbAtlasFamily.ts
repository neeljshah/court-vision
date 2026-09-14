import type { ComparisonEntity } from "./comparisonData";

export type MlbAtlasFamily = "pitch_type" | "team" | "count";
export type MlbAtlasFamilyOption = { family: MlbAtlasFamily; label: string; count: number };

const FAMILY_LABELS: ReadonlyArray<readonly [MlbAtlasFamily, string]> = [
  ["pitch_type", "Pitch types"],
  ["team", "Teams"],
  ["count", "Count states"],
];

export function mlbAtlasFamily(sourceEntity?: string): MlbAtlasFamily | undefined {
  const match = sourceEntity?.match(/^(pitch_type|team|count):.+$/);
  return match?.[1] as MlbAtlasFamily | undefined;
}

export function mlbAtlasFamilyOptions(entities: ComparisonEntity[]): MlbAtlasFamilyOption[] {
  const counts: Record<MlbAtlasFamily, number> = { pitch_type: 0, team: 0, count: 0 };
  for (const entity of entities) {
    const family = mlbAtlasFamily(entity.sourceEntity);
    if (family) counts[family] += 1;
  }
  return FAMILY_LABELS.map(([family, label]) => ({ family, label, count: counts[family] }));
}

export function parseMlbAtlasFamily(value: string | null | undefined): MlbAtlasFamily | undefined {
  return value === "pitch_type" || value === "team" || value === "count" ? value : undefined;
}
