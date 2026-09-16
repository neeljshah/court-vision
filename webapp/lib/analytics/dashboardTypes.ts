export type Sport = "all" | "nba" | "mlb" | "soccer" | "tennis";
export const SPORTS: { id: Sport; label: string }[] = [
  { id: "all", label: "All sports" }, { id: "nba", label: "Basketball" },
  { id: "mlb", label: "Baseball" }, { id: "soccer", label: "Soccer" }, { id: "tennis", label: "Tennis" },
];
export type Module = { id: string; title: string; description: string; category: string; status: string; asOf: string | null };
export type Mechanism = { sport: Sport; mechanism: string; verdict: string; bucket: string; effect: number | null; p: number | null; evidence: string; corpus: string; as_of: string | null };
export type Market = { id: string; sport: Sport; description: string; n_rows: number; scored: boolean; model_brier?: number; market_brier?: number; model_ece?: number; market_ece?: number; reason?: string };
export type HistoryPoint = { sport: Sport; month: string; n: number; model_brier: number; market_brier: number; model_ece: number; market_ece: number };
export type Entity = { name: string; pack: string; sport: Sport; slug: string; asOf: string | null; metrics: { label: string; value: number }[] };
export type Benchmark = { sport: string; market: string; checkpoint: string; n: number; paired_delta_mean: number; paired_delta_95ci: [number, number]; verdict: string; source: string };
export type WalkForward = { acc_mean: number; brier_mean: number; seasons: string[]; folds: { fold: number; acc: number; brier: number; n_train: number; n_val: number }[] };
export type DerivedAnalysis = { id: string; title: string; sport: Sport; rows: number; asOf: string | null };
export type DashboardData = {
  benchmarks: Benchmark[]; walkForward: WalkForward;
  modules: Module[]; mechanisms: Mechanism[]; markets: Market[]; history: HistoryPoint[];
  entities: Entity[]; checks: { pass: number; total: number } | null;
  analyses: DerivedAnalysis[]; recentAnalyses: DerivedAnalysis[];
  pitches: { n: number; distribution: { pitch_type: string; n: number; pct: number }[]; velocity: { pitch_type: string; n: number; p10: number; p50: number; p90: number }[] };
  coverage: { n: number; median: number; rates: { name: string; value: number }[] };
};
export const humanize = (s: string) => s.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
export const number = (n: number) => n.toLocaleString("en-US");
export const dateLabel = (s: string | null) => s ? s.slice(0, 10) : "Date unrecorded";
export const base = process.env.NEXT_PUBLIC_BASE_PATH || "";
export const sourceUrl = (id: string) => `${base}/data/showcase/${id}.json`;
export const moduleUrl = (id: string) => `${base}/analytics/m/${id}/`;
