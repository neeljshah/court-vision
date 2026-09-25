import { field as f, snapshot } from "./labHelpers";
import type { LabDataset, LabRow } from "./labTypes";

type Source = {
  n_pitches?: unknown;
  pitch_type_distribution?: unknown;
  velo_percentiles_by_pitch_type?: unknown;
};
type Entry = Record<string, unknown>;

const entry = (value: unknown): value is Entry =>
  value !== null && typeof value === "object" && !Array.isArray(value);
const finite = (value: unknown): number | null =>
  typeof value === "number" && Number.isFinite(value) ? value : null;
const count = (value: unknown): number | null =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null;
const sourceRows = (value: unknown, field: string): Entry[] => {
  if (!Array.isArray(value)) throw new Error(`statcast_showcase.${field} must be an array`);
  value.forEach((row, index) => {
    if (!entry(row)) throw new Error(`statcast_showcase.${field}[${index}] must be an object`);
  });
  return value as Entry[];
};

export function buildPitchProfilesLabDataset(source: Source): LabDataset {
  const fields = [
    f("p50", "Median velocity", "mph"),
    f("p10", "10th-percentile velocity", "mph"),
    f("p90", "90th-percentile velocity", "mph"),
    f("pct", "Pitch share (%)"),
    f("mix_n", "Pitch-mix observations", "number", 0),
    f("velocity_n", "Velocity observations", "number", 0),
    f("velocity_span", "P90-P10 velocity span", "mph", 1),
    f("velocity_coverage", "Velocity measurement coverage", "percent", 3),
  ];
  const mix = sourceRows(source.pitch_type_distribution, "pitch_type_distribution");
  const velocity = sourceRows(source.velo_percentiles_by_pitch_type, "velo_percentiles_by_pitch_type");
  const rows: LabRow[] = mix.map((raw, mixIndex) => {
    const pitchType = raw.pitch_type;
    const veloIndex = typeof pitchType === "string" && pitchType.length > 0
      ? velocity.findIndex(candidate => candidate.pitch_type === pitchType)
      : -1;
    const measured = veloIndex >= 0 ? velocity[veloIndex] : null;
    const mixN = count(raw.n);
    const velocityN = count(measured?.n);
    const velocitySupported = measured !== null && velocityN !== null && velocityN >= 20;
    const coverageSupported = velocitySupported && mixN !== null && mixN > 0 && velocityN <= mixN;
    const p10 = finite(measured?.p10);
    const p50 = finite(measured?.p50);
    const p90 = finite(measured?.p90);
    const roundedSpan = velocitySupported && p10 !== null && p50 !== null && p90 !== null &&
      p10 >= 0 && p10 <= p50 && p50 <= p90 ? Math.round((p90 - p10) * 10) / 10 : null;
    const span = roundedSpan !== null && Number.isFinite(roundedSpan) ? roundedSpan : null;
    const sourceRows = `statcast_showcase.json pitch_type_distribution[${mixIndex}]` +
      (measured ? ` and velo_percentiles_by_pitch_type[${veloIndex}]` : "");
    const supportNote = !measured
      ? "No matching published velocity row; the velocity denominator is unavailable, not zero."
      : !velocitySupported
        ? "Velocity span and coverage unavailable: velocity_n must be a safe integer at or above the producer's 20-observation floor."
        : !coverageSupported
          ? "Velocity span uses the supported velocity row; coverage unavailable unless mix_n is a positive safe integer and velocity_n <= mix_n."
          : "Velocity measurement coverage = velo_percentiles_by_pitch_type[" + veloIndex +
          "].n / pitch_type_distribution[" + mixIndex +
          "].n; the velocity row independently clears the producer's 20-observation floor.";
    return {
      id: `Published rows-${mixIndex}`,
      label: String(pitchType ?? `Row ${mixIndex + 1}`),
      group: "Published rows",
      values: {
        p50,
        p10,
        p90,
        pct: finite(raw.pct),
        mix_n: mixN,
        velocity_n: velocityN,
        velocity_span: span,
        velocity_coverage: coverageSupported ? velocityN! / mixN! : null,
      },
      note: `Source: ${sourceRows}; matched by pitch_type. ${supportNote} ` +
        "Velocity span = published p90 minus published p10, rounded to 0.1 mph only when p10 <= p50 <= p90 are finite, nonnegative quantiles; the published quantiles were already rounded independently. " +
        "These are pooled pitch-type summaries, not pitcher-level consistency or quality.",
    };
  });
  const total = count(source.n_pitches);
  return {
    id: "pitch-profiles",
    title: "Pitch mix and velocity profiles",
    sport: "mlb",
    category: "Pitch analysis",
    source: "statcast_showcase",
    description: "Compare pitch usage with the center and spread of measured velocity.",
    scope: `${total === null ? "Published pitches (total unavailable)" : `${total.toLocaleString("en-US")} pitches`} from the published 2025 Statcast pull; exact observation dates are not published.`,
    caveat: "Velocity and pitch-mix denominators differ. Missing velocity rows can reflect omitted groups below the 20-observation floor or missing pitch type or speed; they do not prove no pitches were measured. Pooled pitch-type velocity variation is not pitcher consistency or quality, and pitch-type rates do not establish prediction accuracy.",
    status: "Descriptive",
    fields,
    rows,
  };
}

export function getPitchProfilesLabDataset(): LabDataset {
  return buildPitchProfilesLabDataset(snapshot<Source>("statcast_showcase"));
}
