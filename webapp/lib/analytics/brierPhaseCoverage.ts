export type BrierPhaseCoverage = {
  sport: string;
  label: string;
  total: number | null;
  classified: number | null;
  outside: number | null;
  fraction: number | null;
  reason: string | null;
  sourcePaths: string[];
};

type SportDefinition = { label: string; phases: readonly string[] };

const SPORT_DEFINITIONS: Record<string, SportDefinition> = {
  mlb: { label: "MLB", phases: ["early(inn1-3)", "mid(inn4-6)", "late(inn7+)"] },
  soccer_intl: {
    label: "International soccer",
    phases: ["0-15", "15-30", "30-45", "45-60", "60-75", "75-90+"],
  },
};

const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const support = (value: unknown): number | null =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null;

const unavailable = (
  sport: string,
  label: string,
  total: number | null,
  reason: string,
  sourcePaths: string[],
): BrierPhaseCoverage => ({
  sport, label, total, classified: null, outside: null, fraction: null, reason, sourcePaths,
});

/** Describes how published scored rows divide across the generator's named phases. */
export function buildBrierPhaseCoverage(source: { sports?: unknown }): BrierPhaseCoverage[] {
  if (!record(source?.sports)) return [];

  return Object.entries(source.sports).map(([sport, sportValue]) => {
    const definition = Object.hasOwn(SPORT_DEFINITIONS, sport) ? SPORT_DEFINITIONS[sport] : undefined;
    const label = definition?.label ?? sport;
    const allPath = `sports.${sport}.grains.all.n`;

    if (!record(sportValue) || !record(sportValue.grains)) {
      return unavailable(sport, label, null, "Sport grains are missing or malformed.", [allPath]);
    }

    const grains = sportValue.grains;
    const total = record(grains.all) ? support(grains.all.n) : null;
    if (!definition) {
      return unavailable(
        sport, label, total,
        "No published phase partition is defined for this sport.",
        [allPath],
      );
    }

    const phasePaths = definition.phases.map(phase => `sports.${sport}.grains.${phase}.n`);
    const sourcePaths = [allPath, ...phasePaths];
    if (total === null) {
      return unavailable(sport, label, null, "The all-row support is missing or invalid.", sourcePaths);
    }

    const extraPhases = Object.keys(grains).filter(key => key !== "all" && !definition.phases.includes(key));
    if (extraPhases.length) {
      return unavailable(
        sport, label, total,
        `Unexpected phase grains prevent establishing the partition: ${extraPhases.join(", ")}.`,
        [...sourcePaths, ...extraPhases.map(phase => `sports.${sport}.grains.${phase}.n`)],
      );
    }

    const phaseSupports = definition.phases.map(phase => record(grains[phase]) ? support(grains[phase].n) : null);
    if (phaseSupports.some(value => value === null)) {
      return unavailable(sport, label, total, "One or more expected phase supports are missing or invalid.", sourcePaths);
    }

    const classified = (phaseSupports as number[]).reduce((sum, value) => sum + value, 0);
    if (!Number.isSafeInteger(classified) || classified > total) {
      return unavailable(sport, label, total, "The phase supports do not form a valid subset of all scored rows.", sourcePaths);
    }

    return {
      sport,
      label,
      total,
      classified,
      outside: total - classified,
      fraction: total === 0 ? null : classified / total,
      reason: null,
      sourcePaths,
    };
  });
}
