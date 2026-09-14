// Normalization for the static entity comparison page. The browser reads only
// published Atlas artifacts; this module never calculates a rank or fills blanks.

export type RawEntry = {
  entity: string;
  card_path: string;
  key_numbers: Record<string, unknown>;
  as_of?: string;
};

export type RawManifest = { entries?: RawEntry[] };
export type RawPercentiles = {
  packs?: Record<string, {
    n_in_pack?: number;
    fields?: Record<string, { n_ranked?: number }>;
    entities?: Record<string, Record<string, number>>;
  }>;
};
export type RawComparables = {
  packs?: Record<string, {
    entities?: Record<string, { similar?: Array<{ slug: string }> }>;
  }>;
};

export type ComparisonEntity = {
  slug: string;
  name: string;
  values: Record<string, unknown>;
  percentiles: Record<string, number>;
  asOf?: string;
};

export type ComparisonPack = {
  key: string;
  nInPack: number;
  metricKeys: string[];
  entities: ComparisonEntity[];
  suggestedPair?: [string, string];
};

export const COMPARISON_PACKS = [
  { key: "nba_players", label: "NBA players", manifest: "atlas_nba_manifest.json" },
  { key: "nba_teams", label: "NBA teams", manifest: "atlas_nba_teams_manifest.json" },
  { key: "mlb_batters", label: "MLB batters", manifest: "atlas_mlb_batters_manifest.json" },
  { key: "mlb_pitch", label: "MLB pitch types", manifest: "atlas_mlb_pitch_manifest.json" },
  { key: "soccer", label: "Soccer teams", manifest: "atlas_soccer_manifest.json" },
  { key: "tennis", label: "Tennis players", manifest: "atlas_tennis_manifest.json" },
  { key: "calibration", label: "Calibration checkpoints", manifest: "atlas_calibration_manifest.json" },
] as const;

export type ComparisonPackKey = (typeof COMPARISON_PACKS)[number]["key"];

function basename(path: string): string {
  return (path.split(/[\\/]/).pop() || path).replace(/\.[a-z0-9]+$/i, "");
}

function slugify(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
}

// This deliberately matches the player-card route's collision handling.
export function entrySlugs(entries: RawEntry[]): Array<{ slug: string; entry: RawEntry }> {
  const seen = new Set<string>();
  return entries.map((entry) => {
    let slug = basename(entry.card_path);
    if (seen.has(slug)) slug = slugify(entry.entity);
    seen.add(slug);
    return { slug, entry };
  });
}

export function entityName(entry: RawEntry): string {
  const teamName = entry.key_numbers.team_full_name;
  if (typeof teamName === "string" && teamName) return teamName;
  return entry.entity.replace(/^(pitch_type|team):/, "$1 ").replace(/_/g, " ");
}

export function normalizeComparisonPack(
  key: string,
  manifest: RawManifest,
  percentiles: RawPercentiles,
  comparables: RawComparables,
): ComparisonPack {
  const percentilePack = percentiles.packs?.[key];
  const entries = entrySlugs(manifest.entries || []).map(({ slug, entry }) => ({
    slug,
    name: entityName(entry),
    values: entry.key_numbers || {},
    percentiles: percentilePack?.entities?.[slug] || {},
    asOf: entry.as_of,
  }));
  const metricKeys = Object.keys(percentilePack?.fields || {})
    .filter((field) => !/_id$/.test(field));
  const first = entries[0]?.slug;
  const suggested = first && comparables.packs?.[key]?.entities?.[first]?.similar?.[0]?.slug;
  const fallback = entries.find((item) => item.slug !== first)?.slug;
  return {
    key,
    nInPack: percentilePack?.n_in_pack || entries.length,
    metricKeys,
    entities: entries,
    suggestedPair: first && (suggested || fallback) ? [first, suggested || fallback!] : undefined,
  };
}

export function metricLabel(key: string): string {
  return key.replace(/^career_/, "Corpus ").replace(/_career$/, " (corpus)").replace(/_/g, " ")
    .replace(/^seasons played$/, "Seasons in corpus")
    .replace(/\bper36\b/gi, "/ 36").replace(/\bpct\b/gi, "%")
    .replace(/\bfg3\b/gi, "3P").replace(/\bfg\b/gi, "FG")
    .replace(/\bft\b/gi, "FT").replace(/\bpts\b/gi, "PTS")
    .replace(/\breb\b/gi, "REB").replace(/\bast\b/gi, "AST")
    .replace(/\bppg\b/gi, "PPG").replace(/\bga\b/gi, "GA")
    .replace(/\bgd\b/gi, "GD").replace(/\bgf\b/gi, "GF")
    .replace(/\bwr\b/gi, "win rate");
}

export function metricUnit(key: string): string | undefined {
  if (/clay_minus_hard|grass_adapt/.test(key)) return "percentage points";
  if (/pct|_wr_|rate/.test(key)) return "%";
  if (/per36/.test(key)) return "per 36";
  if (/minutes/.test(key)) return "minutes";
  if (/velo/.test(key)) return "mph";
  if (/ppg/.test(key)) return "points per game";
  if (/games/.test(key)) return "games";
  if (/seasons/.test(key)) return "seasons";
  if (/pitches_faced|n_pitches/.test(key)) return "pitches";
  if (/n_batted_balls/.test(key)) return "batted balls";
  if (/n_pitch_types/.test(key)) return "pitch types";
  if (/estimated_woba/.test(key)) return "estimated wOBA";
  return undefined;
}

function roundedMeasurement(value: number, digits: number): string {
  const normalized = Object.is(value, -0) ? 0 : value;
  if (normalized === 0) return "0";
  const rounded = Number(normalized.toFixed(digits));
  if (rounded !== 0) return String(rounded);
  const threshold = 10 ** -digits;
  return normalized > 0 ? `<${threshold}` : `>-${threshold}`;
}

export function formatMetric(value: unknown, key: string): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "Not reported";
  if (/clay_minus_hard|grass_adapt/.test(key)) {
    return `${roundedMeasurement(value * 100, 2)} pp`;
  }
  if (/pct|_wr_|rate/.test(key)) {
    const percent = /_wr_|rate/.test(key) && Math.abs(value) <= 1 ? value * 100 : value;
    const normalized = Object.is(percent, -0) ? 0 : percent;
    return `${Number.isInteger(normalized) ? normalized.toFixed(1) : roundedMeasurement(normalized, 3)}%`;
  }
  const normalized = Object.is(value, -0) ? 0 : value;
  return Number.isInteger(normalized) ? String(normalized) : roundedMeasurement(normalized, 3);
}

export function formatPercentile(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "Not ranked";
  if (!Number.isInteger(value)) return `${value}th percentile`;
  const whole = Math.abs(Math.trunc(value));
  const suffix = whole % 100 >= 11 && whole % 100 <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[whole % 10] || "th";
  return `${value}${suffix} percentile`;
}
