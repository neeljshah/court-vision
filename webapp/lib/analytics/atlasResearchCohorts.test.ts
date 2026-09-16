import { describe, expect, it } from "vitest";
import { getMlbPitchAtlasCohorts } from "./atlasResearchCohorts";
import type { RawEntry } from "./comparisonData";

const entry = (entity: string, key_numbers: Record<string, number>): RawEntry => ({
  entity, card_path: `${entity}.png`, key_numbers,
});

describe("MLB pitch atlas cohorts", () => {
  it("partitions pitch types, teams, and count states with relevant defaults", () => {
    const entries: RawEntry[] = [
      ...Array.from({ length: 19 }, (_, index) => entry(`pitch_type:${index}`, { velo_p50: 90, n_pitches: 100 })),
      ...Array.from({ length: 30 }, (_, index) => entry(`team:${index}`, { n_pitches: 1_000, top_pitch_type_pct: 30 })),
      ...Array.from({ length: 12 }, (_, index) => entry(`count:${index}`, { balls: 1, strikes: 1, n_pitches: 100 })),
    ];
    const cohorts = getMlbPitchAtlasCohorts(entries);

    expect(cohorts.map((cohort) => [cohort.id, cohort.entries.length, cohort.defaultMeasurement])).toEqual([
      ["mlb-pitch-type-atlas-measurements", 19, "velo_p50"],
      ["mlb-team-pitch-atlas-measurements", 30, "n_pitches"],
      ["mlb-count-state-atlas-measurements", 12, "balls"],
    ]);
    expect(new Set(cohorts.flatMap((cohort) => cohort.entries.map((item) => item.entity))).size).toBe(entries.length);
  });
});
