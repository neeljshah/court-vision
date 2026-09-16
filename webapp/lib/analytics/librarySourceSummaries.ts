import type { LibraryAvailability } from "./libraryTypes";

export type PreviewPair = { label: string; value: string };
export type LibrarySourceSummary = {
  asOf: string | null;
  scope: string;
  measurements: PreviewPair[];
  availability: LibraryAvailability;
  previewRows: PreviewPair[][];
};

type Artifact = Record<string, unknown>;
const number = (value: unknown) => typeof value === "number" && Number.isFinite(value) ? value : null;
const label = (key: string) => key.replace(/^n_/, "").replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
const format = (value: number) => value.toLocaleString("en-US", { maximumFractionDigits: Math.abs(value) < 10 ? 2 : 0 });
const measure = (data: Artifact, ...keys: string[]): PreviewPair[] => keys.flatMap(key => {
  const value = number(data[key]); return value === null ? [] : [{ label: label(key), value: format(value) }];
});
const rows = (items: unknown, keys: string[]): PreviewPair[][] => !Array.isArray(items) ? [] : items.slice(0, 2).flatMap(item => {
  if (!item || typeof item !== "object") return [];
  const record = item as Artifact;
  const values = keys.flatMap(key => typeof record[key] === "string" || number(record[key]) !== null
    ? [{ label: label(key), value: typeof record[key] === "string" ? record[key] as string : format(record[key] as number) }] : []);
  return values.length ? [values] : [];
});

type ContainerEvidence = { populated: Array<{ label: string; count: number }>; empty: number; hasScalar: boolean; statuses: string[]; unavailable: boolean };

function isMeasurementContainer(path: string[], items: unknown[]): boolean {
  const key = path[path.length - 1] || "";
  return items.some(item => item && typeof item === "object") || path[0] === "sports"
    || /rows|entries|players|teams|cells|table|distribution|buckets|observations|top_|bottom_|by_|frequencies/.test(key);
}

function populationLabel(path: string[], items: unknown[]): string {
  const last = path[path.length - 1] || "rows";
  const sample = items.find(item => item && typeof item === "object") as Artifact | undefined;
  const noun = sample && "bucket" in sample ? "buckets" : /^(top|bottom)_\d+$/.test(last) ? "player rows" : "rows";
  if (path.length >= 2 && path[0] === "sports") {
    const sport = path[1] === "mlb" ? "MLB" : path[1] === "nba" ? "NBA" : label(path[1]);
    return `${sport} ${items.length} ${noun}`;
  }
  if (/^(top|bottom)_\d+$/.test(last)) return `${label(last).toLowerCase()} ${noun}`;
  return `${label(last)} ${items.length} ${noun}`;
}

function inspectContainers(value: unknown, path: string[] = [], evidence: ContainerEvidence = { populated: [], empty: 0, hasScalar: false, statuses: [], unavailable: false }): ContainerEvidence {
  if (Array.isArray(value)) {
    if (!isMeasurementContainer(path, value)) return evidence;
    if (value.length) evidence.populated.push({ label: populationLabel(path, value), count: value.length });
    else evidence.empty += 1;
    return evidence;
  }
  if (!value || typeof value !== "object") return evidence;
  for (const [key, child] of Object.entries(value as Artifact)) {
    if (key === "status" && typeof child === "string") evidence.statuses.push(child.toLowerCase());
    if (key === "not_buildable" && child === true) evidence.unavailable = true;
    if (number(child) !== null) evidence.hasScalar = true;
    if (child && typeof child === "object") inspectContainers(child, [...path, key], evidence);
  }
  return evidence;
}

function scalarFacts(data: Artifact): PreviewPair[] {
  const found: PreviewPair[] = [];
  const visit = (value: unknown, path: string[] = []) => {
    if (Array.isArray(value) || !value || typeof value !== "object" || found.length >= 4) return;
    for (const [key, child] of Object.entries(value as Artifact)) {
      if (number(child) !== null && found.length < 4) found.push({ label: label([...path, key].join(" ")), value: format(child as number) });
      else if (child && typeof child === "object") visit(child, [...path, key]);
    }
  };
  visit(data);
  return found;
}

function genericSummary(data: Artifact): Pick<LibrarySourceSummary, "scope" | "measurements" | "previewRows"> {
  const evidence = inspectContainers(data);
  const topLevelArrays = Object.entries(data).filter(([, value]) => Array.isArray(value))
    .map(([key, value]) => ({ label: label(key), value: `${(value as unknown[]).length.toLocaleString("en-US")} entries` }));
  const facts = [...scalarFacts(data), ...topLevelArrays].slice(0, 4);
  const scope = evidence.populated.length ? evidence.populated.slice(0, 2).map(item => item.label).join(", ")
    : facts.length ? facts.slice(0, 2).map(item => `${item.value} ${item.label.toLowerCase()}`).join(", ") : "No published measurements";
  return { scope, measurements: facts, previewRows: [] };
}

function adapter(id: string, data: Artifact): Pick<LibrarySourceSummary, "scope" | "measurements" | "previewRows"> | null {
  switch (id) {
    case "statcast_showcase": return { scope: `${format(data.n_pitches as number)} pitches, ${(data.pitch_type_distribution as unknown[]).length} pitch types`, measurements: measure(data, "n_pitches"), previewRows: rows(data.pitch_type_distribution, ["pitch_type", "n", "pct"]) };
    case "ctx_player_splits": return { scope: `${(data.coverage as Artifact).players_analysed} players, ${(data.coverage as Artifact).seasons} seasons`, measurements: measure(data.coverage as Artifact, "players_analysed", "seasons"), previewRows: rows(data.players, ["player_name", "total_games", "overall_ts_pct", "context_sensitivity_score"]) };
    case "ctx_lineup_proxy": return { scope: `${format(data.n_qualified as number)} qualified players, 2025-26`, measurements: measure(data, "n_qualified"), previewRows: rows(data.players, ["player_name", "n_active", "delta_win_rate"]) };
    case "on_off_showcase": { const seasons = data.seasons as Artifact; const first = Object.values(seasons)[0] as Artifact; return { scope: `${Object.keys(seasons).length} seasons: ${(first.top_15 as unknown[]).length} top and ${(first.bottom_15 as unknown[]).length} bottom player rows`, measurements: measure(first, "n_considered", "n_ranked"), previewRows: rows(first.top_15, ["player_name", "net_rating_delta", "min_on"]) }; }
    case "comeback_atlas": return { scope: `${format(data.n_buckets_unmasked as number)} published buckets, ${format(data.n_buckets_total as number)} total`, measurements: measure(data, "n_buckets_total", "n_buckets_unmasked", "n_buckets_masked_n_lt_30"), previewRows: rows(data.cells, ["label", "n_games", "model_brier"]) };
    case "schedule_density": return { scope: `${(data.per_team_season_frequencies as unknown[]).length} team-seasons`, measurements: [{ label: "Team seasons", value: String((data.per_team_season_frequencies as unknown[]).length) }], previewRows: rows(data.per_team_season_frequencies, ["team", "season", "games"]) };
    case "pitch_sequencing": return { scope: `${format(data.n_pitches_kept as number)} pitches, ${format(data.n_transitions as number)} transitions`, measurements: measure(data, "n_pitches_total", "n_pitches_kept", "n_transitions"), previewRows: (data.pitch_types as unknown[]).slice(0, 2).map(value => [{ label: "Pitch Type", value: String(value) }]) };
    case "mlb_velo_bands": return { scope: `${format(data.n_analyzed as number)} pitches, ${(data.chart_pitch_types as unknown[]).length} charted pitch types`, measurements: measure(data, "n_pitches_raw", "n_analyzed"), previewRows: rows(data.velo_band_shares_by_pitch_type, ["pitch_type", "n", "median_velo"]) };
    case "mlb_count_leverage": return { scope: `${format(data.n_pitches_valid_count as number)} pitches, ${(data.by_exact_count as unknown[]).length} counts`, measurements: measure(data, "n_pitches_total", "n_pitches_valid_count"), previewRows: rows(data.by_leverage_class, ["class", "n", "pitch_type_n"]) };
    case "cf_star_removal": return { scope: `${format(data.n_teams as number)} teams, 2024-25`, measurements: measure(data, "n_teams"), previewRows: rows(data.teams, ["team_abbr", "player_name", "delta_winprob"]) };
    case "lineup_synergy": return { scope: `${format(data.n_qualified as number)} qualified five-man lineups, ${String(data.season)}`, measurements: measure(data, "n_qualified"), previewRows: rows(data.top, ["n_games", "net_per48", "synergy_residual"]) };
    case "rim_deterrence": return { scope: `${(data.seasons as unknown[]).reduce<number>((sum, season) => sum + Number((season as Artifact).n_qualified || 0), 0)} qualified player-seasons, ${(data.seasons as unknown[]).length} seasons`, measurements: [{ label: "Seasons", value: String((data.seasons as unknown[]).length) }], previewRows: rows(data.seasons, ["season", "n_qualified", "min_on_floor"]) };
    default: return null;
  }
}

export function summarizeLibrarySource(id: string, data: Artifact, manifestStatus?: string): LibrarySourceSummary {
  const detail = adapter(id, data) || genericSummary(data);
  const evidence = inspectContainers(data);
  const status = String(data.status || manifestStatus || "").toLowerCase();
  const nestedStatus = evidence.unavailable || evidence.statuses.some(value => value !== status && /not_buildable|unavailable|partial/.test(value));
  const explicitlyUnavailable = data.not_buildable === true || /not_buildable|unavailable/.test(status);
  const availability: LibraryAvailability = explicitlyUnavailable || (!evidence.populated.length && !evidence.hasScalar) ? "unavailable"
    : evidence.empty > 0 || status === "partial" || nestedStatus ? "partial" : "published";
  const asOf = [data.as_of, data.generated_at, data.created_at].find(value => typeof value === "string") as string | undefined;
  return { asOf: asOf || null, availability, ...detail };
}
