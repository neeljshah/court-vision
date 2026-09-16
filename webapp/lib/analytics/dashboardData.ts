import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { DashboardData, Entity, HistoryPoint, Market, Mechanism, Module, Sport } from "./dashboardTypes";
import { getResearchAnalyses } from "./researchData";

const directory = join(process.cwd(), "public/data/showcase");
// These versioned, public artifacts are required: a missing source must fail the build.
function read<T>(name: string): T {
  const text = readFileSync(join(directory, `${name}.json`), "utf8");
  // Python exports contain bare NaN. Preserve quoted prose and missing values.
  return JSON.parse(text.replace(/"(?:\\.|[^"\\])*"|\bNaN\b/g, token => token === "NaN" ? "null" : token));
}
export function moduleCategory(id: string): string {
  if (/^novel_/.test(id)) return "Novel metrics";
  if (/calib|brier|murphy|residual|forecast|sharpness/.test(id)) return "Model quality";
  if (/market|bookmaker|vig|line_|odds|favorite|closing/.test(id)) return "Markets";
  if (/agent|fleet|loop|verdict|mechanism/.test(id)) return "Research";
  if (/coverage|completeness|missing|statcast/.test(id)) return "Data coverage";
  return "Player & team analysis";
}
const ledgerSport: Record<string, Sport> = { basketball_nba: "nba", mlb: "mlb", soccer: "soccer", tennis: "tennis" };
const packs: { file: string; pack: string; sport: Sport; fields: string[] }[] = [
  { file: "nba", pack: "nba_players", sport: "nba", fields: ["career_pts_per36", "career_ast_per36", "career_games"] },
  { file: "nba_teams", pack: "nba_teams", sport: "nba", fields: ["ppg_latest_season", "pace_proxy_latest_season"] },
  { file: "mlb_batters", pack: "mlb_batters", sport: "mlb", fields: ["avg_exit_velo", "pitches_faced"] },
  { file: "mlb_pitch", pack: "mlb_pitch", sport: "mlb", fields: ["velo_p50", "top_pitch_type_pct", "n_pitches"] },
  { file: "soccer", pack: "soccer", sport: "soccer", fields: ["ppg_l10", "gd_l10"] },
  { file: "tennis", pack: "tennis", sport: "tennis", fields: ["hard_wr_career", "clay_wr_career"] },
  { file: "calibration", pack: "calibration", sport: "all", fields: ["model_ece", "market_ece"] },
];
export function getDashboardData(): DashboardData {
  const manifest = read<{ modules: { id: string; title: string; one_line: string; status: string; as_of: string | null }[]; checks_green?: { pass: number; total: number } }>("site_manifest");
  const modules: Module[] = manifest.modules.map(m => ({ id: m.id, title: m.title, description: m.one_line, category: moduleCategory(m.id), status: m.status, asOf: m.as_of }));
  const ledger = read<{ by_sport: Record<string, { mechanisms: Omit<Mechanism, "sport">[] }> }>("mechanism_ledger_export");
  const mechanisms = Object.entries(ledger.by_sport).flatMap(([sport, data]) => {
    if (!ledgerSport[sport]) throw new Error(`Unknown ledger sport: ${sport}`);
    return data.mechanisms.map(m => ({ ...m, sport: ledgerSport[sport] }));
  });
  const marketData = read<{ market_types: Record<string, Omit<Market, "id" | "sport">> }>("calibration_by_market_type");
  const markets: Market[] = Object.entries(marketData.market_types).map(([id, m]) => ({ ...m, id, sport: id.startsWith("mlb") ? "mlb" : "soccer" }));
  const historyData = read<Record<string, Record<string, Omit<HistoryPoint, "sport" | "month">>>>("calibration_over_time");
  const history: HistoryPoint[] = Object.entries(historyData).flatMap(([sport, months]) => Object.entries(months).map(([month, point]) => ({ ...point, month, sport: sport === "mlb" ? "mlb" : "soccer" })));
  const entities: Entity[] = packs.flatMap(pack => {
    const atlas = read<{ entries: { entity: string; sport?: string; card_path: string; key_numbers: Record<string, unknown>; as_of: string | null }[] }>(`atlas_${pack.file}_manifest`);
    const seen = new Set<string>();
    return atlas.entries.map(e => {
      let slug = e.card_path.split("/").pop()!.replace(/\.png$/, "");
      if (seen.has(slug)) slug = e.entity.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
      seen.add(slug);
      const sport: Sport = pack.pack === "calibration" ? (e.sport === "mlb" ? "mlb" : "soccer") : pack.sport;
      return {
      name: typeof e.key_numbers.team_full_name === "string" ? e.key_numbers.team_full_name : e.entity.replace(/_/g, " "), pack: pack.pack, sport, slug, asOf: e.as_of || null,
      metrics: (pack.fields.length ? pack.fields : Object.keys(e.key_numbers).filter(k => !/id$/.test(k))).filter(k => typeof e.key_numbers[k] === "number" && Number.isFinite(e.key_numbers[k])).slice(0, 3).map(k => ({ label: k.replace(/^career_/, "corpus_"), value: e.key_numbers[k] as number })),
    }; });
  });
  const pitches = read<{ n_pitches: number; pitch_type_distribution: DashboardData["pitches"]["distribution"]; velo_percentiles_by_pitch_type: DashboardData["pitches"]["velocity"] }>("statcast_showcase");
  const coverage = read<{ dossiers_count: number; median_completeness_score: number; category_fill_rate: Record<string, number> }>("dossier_completeness");
  const analyses = getResearchAnalyses().map(analysis => ({ id: analysis.id, title: analysis.title, sport: analysis.sport, rows: analysis.rows.length, asOf: analysis.asOf || null }));
  const recentAnalyses = [...analyses].sort((left, right) => (right.asOf || "").localeCompare(left.asOf || "")).slice(0, 6);
  return { modules, mechanisms, markets, history, entities, checks: manifest.checks_green || null,
    analyses, recentAnalyses,
    benchmarks: read<{ rows: DashboardData["benchmarks"] }>("cross_sport_scoreboard").rows,
    walkForward: read<DashboardData["walkForward"]>("forecaster/winprob_walk_forward_results"),
    pitches: { n: pitches.n_pitches, distribution: pitches.pitch_type_distribution, velocity: pitches.velo_percentiles_by_pitch_type },
    coverage: { n: coverage.dossiers_count, median: coverage.median_completeness_score, rates: Object.entries(coverage.category_fill_rate).map(([name, value]) => ({ name, value })).sort((a, b) => b.value - a.value) },
  };
}
