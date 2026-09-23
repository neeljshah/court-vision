import { field as f, labRows } from "./labHelpers";
import type { ResearchAnalysis, ResearchField } from "./researchTypes";

type Entry = Record<string, unknown>;
type MixRow = { pitch_type: string; n: number; pct: number };
type Statcast = { n_pitches: number; pitch_type_distribution: MixRow[] };
const ATLAS = "atlas_mlb_pitch_manifest";
const STATCAST = "statcast_showcase";
const COUNT_PATH = `${ATLAS}.entries[pitch_type].key_numbers.count_state_pct`;
const COUNTS = Array.from({ length: 4 }, (_, balls) => [0, 1, 2].map(strikes => `${balls}-${strikes}`)).flat();
const TWO_STRIKE = ["0-2", "1-2", "2-2", "3-2"];
// Twelve percentages rounded to two decimals can differ from 100 by at most 0.06.
const ROUNDING_TOLERANCE = 0.061;
const record = (value: unknown): Entry => value !== null && typeof value === "object" && !Array.isArray(value) ? value as Entry : {};
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const percentage = (value: unknown): value is number => finite(value) && value >= 0 && value <= 100;
const positiveCount = (value: unknown): value is number => finite(value) && Number.isSafeInteger(value) && value > 0;
const sourced = (sourceId: string, key: string, label: string, unit: ResearchField["unit"], digits = 2): ResearchField => ({ ...f(key, label, unit, digits), sourceId });

function pitchEntries(atlas: unknown): Entry[] {
  const entries = record(atlas).entries;
  return Array.isArray(entries) ? entries.map(record).filter(entry => typeof entry.entity === "string" && entry.entity.startsWith("pitch_type:")) : [];
}

function reconcile(statcast: Statcast, entries: Entry[]): boolean {
  const mix = statcast.pitch_type_distribution;
  if (!positiveCount(statcast.n_pitches) || mix.length === 0 || mix.length !== entries.length) return false;
  const codes = new Set(mix.map(row => row.pitch_type));
  const atlasCodes = new Set(entries.map(entry => entry.entity));
  if (codes.size !== mix.length || atlasCodes.size !== entries.length) return false;
  if (mix.some(row => !row.pitch_type || !positiveCount(row.n) || !percentage(row.pct))) return false;
  if (mix.reduce((sum, row) => sum + row.n, 0) !== statcast.n_pitches) return false;
  return mix.every(row => {
    const numbers = record(entries.find(entry => entry.entity === `pitch_type:${row.pitch_type}`)?.key_numbers);
    return numbers.n_pitches === row.n && numbers.pct_of_all_pitches === row.pct;
  });
}

function countContext(value: unknown, joined: boolean) {
  const counts = record(value);
  const keys = Object.keys(counts);
  const valid = keys.length > 0 && keys.every(key => COUNTS.includes(key) && percentage(counts[key]));
  const total = valid ? keys.reduce((sum, key) => sum + (counts[key] as number), 0) : NaN;
  const complete = keys.length === COUNTS.length;
  const coherent = valid && total <= 100 + ROUNDING_TOLERANCE && (!complete || Math.abs(total - 100) <= ROUNDING_TOLERANCE);
  const empty = { first_pitch_share: null, two_strike_share: null, peak_count_share: null, count_states: null, peak_count: null };
  if (!joined) return { ...empty, reason: "Count context unavailable: source pitch codes, counts or overall shares do not reconcile." };
  if (!coherent) return { ...empty, reason: "Count context unavailable: published count distribution is missing or invalid." };
  const peak = complete ? Math.max(...keys.map(key => counts[key] as number)) : null;
  const peakCount = peak === null ? null : COUNTS.filter(key => counts[key] === peak).join(", ");
  return {
    first_pitch_share: percentage(counts["0-0"]) ? counts["0-0"] / 100 : null,
    two_strike_share: TWO_STRIKE.every(key => percentage(counts[key])) ? TWO_STRIKE.reduce((sum, key) => sum + (counts[key] as number), 0) / 100 : null,
    peak_count_share: peak === null ? null : peak / 100,
    count_states: keys.length,
    peak_count: peakCount,
    reason: complete ? "All 12 count shares published." : `${keys.length}/12 count shares published; omitted counts remain unavailable. Peak requires all 12; two-strike share requires all four two-strike counts.`,
  };
}

export function buildPitchMixResearch(statcast: Statcast, atlas: unknown): ResearchAnalysis {
  const entries = pitchEntries(atlas);
  const joined = reconcile(statcast, entries);
  const fields: ResearchField[] = [
    sourced(STATCAST, "share", "Pitch share", "percent"),
    sourced(STATCAST, "squared_share", "HHI contribution", "number", 4),
    sourced(STATCAST, "n", "Pitches", "number", 0),
    sourced(ATLAS, "first_pitch_share", "0-0 share within pitch type", "percent"),
    sourced(ATLAS, "two_strike_share", "Two-strike share within pitch type", "percent"),
    sourced(ATLAS, "peak_count_share", "Peak count share within pitch type", "percent"),
    sourced(ATLAS, "count_states", "Published count states (of 12)", "number", 0),
  ];
  const mix = statcast.pitch_type_distribution.map(row => {
    const entry = entries.find(item => item.entity === `pitch_type:${row.pitch_type}`);
    const context = countContext(record(entry?.key_numbers).count_state_pct, joined);
    const asOf = typeof entry?.as_of === "string" ? entry.as_of : "not published";
    return {
      ...row, ...context, label: row.pitch_type, share: row.pct / 100, squared_share: (row.pct / 100) ** 2, asOf,
      note: `League pitch share denominator: ${statcast.n_pitches.toLocaleString("en-US")} pitches. Count shares are within pitch type ${row.pitch_type} (n=${row.n.toLocaleString("en-US")}); exact per-count event totals are not published. Peak count: ${context.peak_count ?? "unavailable"}. ${context.reason} Atlas as of ${asOf}; Statcast local 2025 pull, exact observation dates not published.${row.n < 1000 ? " Fewer than 1,000 pitches; sparse descriptive support, not a comparison confidence threshold." : ""}${row.pitch_type === "UNK" ? " UNK retains missing pitch classifications." : ""}`,
    };
  });
  const hhi = mix.reduce((sum, row) => sum + row.squared_share, 0);
  const dates = [...new Set(mix.map(row => row.asOf))].sort();
  return {
    id: "mlb-pitch-mix-concentration", title: "Pitch Mix Concentration", sport: "mlb", category: "Pitch matchup context",
    source: STATCAST, status: "Descriptive", novelty: "Derived analysis", fields,
    description: "Explore league pitch-type concentration alongside the counts in which each pitch type appears.",
    question: "Which pitch types dominate this league snapshot, and how is each type distributed across pre-pitch ball-strike counts?",
    scope: `All ${mix.length} published pitch-type rows from the local 2025 Statcast pull (${statcast.n_pitches.toLocaleString("en-US")} pitches). ${joined ? "Both public sources match on every pitch code, pitch count and rounded overall share." : "Public source reconciliation failed; added count context remains unavailable."}`,
    caveat: "League aggregates mix pitchers, roles and dates; they do not describe an individual pitcher or a matchup forecast. Count shares divide by pitches of that type, not all pitches in that count. Missing count keys are unavailable, not zero; exact event totals cannot be reconstructed from rounded percentages. Small categories carry high sampling noise and are shown for completeness, not comparison. UNK includes missing classifications. Matching totals do not establish matching observation dates: Statcast publishes only a local 2025 pull, while the Atlas separately publishes its as-of date.",
    method: "Join exact pitch codes only after both sources reconcile one-to-one on all codes, raw counts, rounded overall shares and the Statcast total. Retain the original league mix if this check fails. Accept count percentages only for legal pre-pitch states and valid published totals; allow 0.06 percentage points of rounding across 12 cells. Never fill an omitted state with zero.",
    rows: labRows(mix, fields, "label", `HHI=${hhi.toFixed(4)}`).map((row, index) => ({
      ...row, bindingValues: { peak_count: mix[index].peak_count, atlas_as_of: mix[index].asOf },
      sourcePaths: [`${STATCAST}.pitch_type_distribution[pitch_type=${row.label}]`, `${ATLAS}.entries[entity=pitch_type:${row.label}].key_numbers.count_state_pct`],
    })),
    sources: [
      { id: STATCAST, asOf: "not published; local 2025 pull", fields: ["share", "squared_share", "n"] },
      { id: ATLAS, asOf: dates.join("; ") || "not published", fields: ["first_pitch_share", "two_strike_share", "peak_count_share", "count_states"] },
    ],
    formula: "league_share = published pct / 100; HHI = sum(league_share^2); row contribution = league_share^2. first_pitch_share = count_state_pct[0-0] / 100. two_strike_share = sum(count_state_pct[0-2, 1-2, 2-2, 3-2]) / 100, requiring all four cells. peak_count_share = max(all 12 published count_state_pct cells) / 100; tied peak counts are all retained. count_states = number of valid explicitly published count cells, not event counts. All count shares use pitches of that type as their denominator.",
    bindings: [
      { operand: "league_share", sourcePath: `${STATCAST}.pitch_type_distribution[].pct / 100`, valueKey: "share", label: "League pitch share" },
      { operand: "n", sourcePath: `${STATCAST}.pitch_type_distribution[].n`, valueKey: "n", label: "Pitches of this type" },
      { operand: "first_pitch_share", sourcePath: `${COUNT_PATH}[0-0] / 100`, valueKey: "first_pitch_share", label: "0-0 share within pitch type" },
      { operand: "two_strike_share", sourcePath: `${COUNT_PATH}[0-2,1-2,2-2,3-2] / 100 (sum)`, valueKey: "two_strike_share", label: "Two-strike share within pitch type" },
      { operand: "peak_count_share", sourcePath: `${COUNT_PATH} (maximum of all 12) / 100`, valueKey: "peak_count_share", label: "Peak count share within pitch type" },
      { operand: "peak_count", sourcePath: `${COUNT_PATH} (keys tied for maximum)`, valueKey: "peak_count", label: "Peak ball-strike count" },
      { operand: "count_states", sourcePath: `${COUNT_PATH} (published keys)`, valueKey: "count_states", label: "Published count states (of 12)" },
      { operand: "atlas_as_of", sourcePath: `${ATLAS}.entries[].as_of`, valueKey: "atlas_as_of", label: "Atlas as of" },
    ],
    interpretation: "Pitch share and HHI describe concentration across pitch types. Count shares describe where a given pitch type appears: a 30% two-strike share means 30% of that type's pitches had two strikes before the pitch. It does not mean that type was chosen for 30% of all two-strike pitches. Read raw support and missing count coverage before comparing types; these frequencies do not measure effectiveness.",
    references: [
      { title: "Statcast CSV documentation: pitch_type, balls and strikes", url: "https://baseballsavant.mlb.com/csv-docs" },
      { title: "Published CourtVision MLB pitch Atlas", url: "https://github.com/neeljshah/court-vision/blob/master/webapp/public/data/showcase/atlas_mlb_pitch_manifest.json" },
    ],
  };
}
