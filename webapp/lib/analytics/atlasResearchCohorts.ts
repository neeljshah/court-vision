import type { RawEntry } from "./comparisonData";

export type AtlasResearchCohort = {
  id: string;
  title: string;
  noun: string;
  defaultMeasurement: string;
  entries: RawEntry[];
  sourceIndexes: number[];
};

type CohortDefinition = Omit<AtlasResearchCohort, "entries" | "sourceIndexes"> & {
  prefixes: string[];
  defaultMeasurements: string[];
};

const MLB_PITCH_COHORTS: CohortDefinition[] = [
  {
    id: "mlb-pitch-type-atlas-measurements",
    title: "MLB pitch type atlas measurements",
    noun: "MLB pitch types",
    prefixes: ["pitch_type"],
    defaultMeasurements: ["velo_p50", "n_pitches"],
    defaultMeasurement: "velo_p50",
  },
  {
    id: "mlb-team-pitch-atlas-measurements",
    title: "MLB team pitch atlas measurements",
    noun: "MLB pitching teams",
    prefixes: ["team"],
    defaultMeasurements: ["n_pitches", "top_pitch_type_pct"],
    defaultMeasurement: "n_pitches",
  },
  {
    id: "mlb-count-state-atlas-measurements",
    title: "MLB count state atlas measurements",
    noun: "MLB count states",
    prefixes: ["count"],
    defaultMeasurements: ["balls", "strikes", "n_pitches"],
    defaultMeasurement: "balls",
  },
];

function prefix(entry: RawEntry): string {
  return entry.entity.split(":", 1)[0];
}

function firstPublishedMeasurement(entries: RawEntry[], keys: string[]): string {
  return keys.find((key) => entries.some((entry) => {
    const value = entry.key_numbers?.[key];
    return typeof value === "number" && Number.isFinite(value);
  })) || keys[0];
}

export function getMlbPitchAtlasCohorts(entries: RawEntry[]): AtlasResearchCohort[] {
  return MLB_PITCH_COHORTS.map((definition) => {
    const selected = entries.flatMap((entry, index) => (
      definition.prefixes.includes(prefix(entry)) ? [{ entry, index }] : []
    ));
    return {
      id: definition.id,
      title: definition.title,
      noun: definition.noun,
      defaultMeasurement: firstPublishedMeasurement(selected.map((item) => item.entry), definition.defaultMeasurements),
      entries: selected.map((item) => item.entry),
      sourceIndexes: selected.map((item) => item.index),
    };
  });
}
