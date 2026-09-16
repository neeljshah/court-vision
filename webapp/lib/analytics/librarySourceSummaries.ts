export type PreviewPair = { label: string; value: string };
export type LibrarySourceSummary = {
  asOf: string | null;
  scope: string;
  measurements: PreviewPair[];
  availability: "published" | "partial" | "unavailable";
  previewRows: PreviewPair[][];
};

type Artifact = Record<string, unknown>;
const number = (value: unknown) => typeof value === "number" && Number.isFinite(value) ? value : null;
const integer = (value: unknown) => number(value) !== null && Number.isInteger(value as number) ? value as number : null;
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

function genericSummary(data: Artifact): Pick<LibrarySourceSummary, "scope" | "measurements" | "previewRows"> {
  const numbers = Object.entries(data).filter(([, value]) => integer(value) !== null).slice(0, 4)
    .map(([key, value]) => ({ label: label(key), value: format(value as number) }));
  const arrays = Object.entries(data).filter(([, value]) => Array.isArray(value));
  const arrayFacts = arrays.slice(0, Math.max(0, 4 - numbers.length)).map(([key, value]) => ({ label: label(key), value: `${(value as unknown[]).length.toLocaleString("en-US")} entries` }));
  const firstRows = arrays.flatMap(([, value]) => rows(value, Object.keys((value as unknown[])[0] || {}).slice(0, 3))).slice(0, 2);
  const facts = [...numbers, ...arrayFacts];
  return { scope: facts.length ? facts.slice(0, 2).map(f => `${f.value} ${f.label.toLowerCase()}`).join(", ") : "Published artifact", measurements: facts, previewRows: firstRows };
}

function adapter(id: string, data: Artifact): Pick<LibrarySourceSummary, "scope" | "measurements" | "previewRows"> | null {
  switch (id) {
    case "statcast_showcase": return { scope: `${format(data.n_pitches as number)} pitches, ${(data.pitch_type_distribution as unknown[]).length} pitch types`, measurements: measure(data, "n_pitches"), previewRows: rows(data.pitch_type_distribution, ["pitch_type", "n", "pct"]) };
    case "ctx_player_splits": return { scope: `${(data.coverage as Artifact).players_analysed} players, ${(data.coverage as Artifact).seasons} seasons`, measurements: measure(data.coverage as Artifact, "players_analysed", "seasons"), previewRows: rows(data.players, ["player_name", "total_games", "overall_ts_pct", "context_sensitivity_score"]) };
    case "ctx_lineup_proxy": return { scope: `${format(data.n_qualified as number)} qualified players, 2025-26`, measurements: measure(data, "n_qualified"), previewRows: rows(data.players, ["player_name", "n_active", "delta_win_rate"]) };
    case "on_off_showcase": { const seasons = data.seasons as Artifact; const first = Object.values(seasons)[0] as Artifact; return { scope: `${Object.keys(seasons).length} seasons of on/off context`, measurements: measure(first, "n_considered", "n_ranked"), previewRows: rows(first.top_15, ["player_name", "net_rating_delta", "min_on"]) }; }
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
  const status = String(data.status || manifestStatus || "").toLowerCase();
  const hasRows = Object.values(data).some(value => Array.isArray(value) && value.length > 0);
  const availability = data.not_buildable === true || /not_buildable|unavailable/.test(status) || !hasRows ? "unavailable" : status === "partial" ? "partial" : "published";
  const asOf = [data.as_of, data.generated_at, data.created_at].find(value => typeof value === "string") as string | undefined;
  return { asOf: asOf || null, availability, ...detail };
}
