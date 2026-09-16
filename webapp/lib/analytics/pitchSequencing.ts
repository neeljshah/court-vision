type RecordValue = Record<string, unknown>;

export interface PitchSequencingClass {
  id: string;
  definition: string;
  overlapping: boolean;
  coverage: number | null;
  rowNFrom: Array<number | null>;
  rowBelowFloor: boolean[];
  countMatrix: Array<Array<number | null>>;
  probabilityMatrix: Array<Array<number | null>>;
}

export interface PitchSequencingData {
  pitchTypes: string[];
  classes: PitchSequencingClass[];
  rowMinN: number | null;
  asOf: string | null;
}

export interface PitchCell {
  from: string;
  to: string;
  count: number | null;
  denominator: number | null;
  probability: number | null;
  masked: boolean;
}

function record(value: unknown): RecordValue | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as RecordValue : null;
}

function numberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function matrix(value: unknown, size: number): Array<Array<number | null>> {
  if (!Array.isArray(value)) return [];
  return value.slice(0, size).map(row => Array.isArray(row) ? row.slice(0, size).map(numberOrNull) : []);
}

function classFrom(value: unknown, size: number): PitchSequencingClass | null {
  const raw = record(value);
  const id = typeof raw?.class === "string" ? raw.class : null;
  if (!raw || !id) return null;
  return {
    id,
    definition: typeof raw.definition === "string" ? raw.definition : "Not published",
    overlapping: raw.overlapping === true,
    coverage: numberOrNull(raw.coverage),
    rowNFrom: Array.isArray(raw.row_n_from) ? raw.row_n_from.slice(0, size).map(numberOrNull) : [],
    rowBelowFloor: Array.isArray(raw.row_below_floor) ? raw.row_below_floor.slice(0, size).map(item => item === true) : [],
    countMatrix: matrix(raw.count_matrix, size),
    probabilityMatrix: matrix(raw.prob_matrix, size),
  };
}

/** Parses the committed pitch-sequencing artifact without changing any matrix values. */
export function buildPitchSequencing(value: unknown): PitchSequencingData {
  const raw = record(value);
  const pitchTypes = Array.isArray(raw?.pitch_types) ? raw.pitch_types.filter((item): item is string => typeof item === "string") : [];
  const classes = Array.isArray(raw?.by_class) ? raw.by_class.map(item => classFrom(item, pitchTypes.length)).filter((item): item is PitchSequencingClass => item !== null) : [];
  const floors = record(raw?.floors);
  return {
    pitchTypes,
    classes,
    rowMinN: numberOrNull(floors?.row_min_n),
    asOf: typeof raw?.as_of === "string" ? raw.as_of : null,
  };
}

/** Returns one published row/column intersection; the probability is never renormalized. */
export function pitchCell(data: PitchSequencingData, selected: PitchSequencingClass, row: number, column: number): PitchCell | null {
  const from = data.pitchTypes[row];
  const to = data.pitchTypes[column];
  if (!from || !to) return null;
  return {
    from,
    to,
    count: selected.countMatrix[row]?.[column] ?? null,
    denominator: selected.rowNFrom[row] ?? null,
    probability: selected.probabilityMatrix[row]?.[column] ?? null,
    masked: selected.rowBelowFloor[row] === true,
  };
}
