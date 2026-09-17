// Pure field selection for the experimental-measurement cards. Artifacts use
// several published shapes, so this module deliberately contains no filesystem
// access and can be checked with small fixtures.

type Row = Record<string, unknown>;
export type CardVerdict = "confirmed" | "null" | "contradicted" | "descriptive";

export interface NovelMeasurement {
  lead: string;
  leadLabel: string;
  denominator: string;
  interval?: string;
  verdict: CardVerdict;
  result: string;
  limitation: string;
}

const record = (value: unknown): Row =>
  value && typeof value === "object" && !Array.isArray(value) ? value as Row : {};
const rows = (value: unknown): Row[] => Array.isArray(value) ? value.map(record) : [];
const text = (value: unknown): string => value == null ? "" : String(value);
const number = (value: unknown): string => text(value);
const count = (value: unknown): string => Number(value).toLocaleString("en-US");
const interval = (value: unknown): string | undefined => {
  const values = Array.isArray(value) ? value : [];
  return values.length === 2 ? `[${number(values[0])}, ${number(values[1])}]` : undefined;
};
const largest = (items: Row[], field: string): Row =>
  items.reduce((best, item) => Number(item[field]) > Number(best[field]) ? item : best, items[0] || {});
const first = (...values: unknown[]): string => values.map(text).find(Boolean) || "";
const firstConfound = (value: unknown): unknown => Array.isArray(value) ? value[0] : undefined;
const sentence = (value: string): string => value.match(/^.*?[.!?](?:\s|$)/)?.[0].trim() || value;
const limitation = (artifact: Row): string => sentence(first(artifact.caveat, firstConfound(artifact.declared_confounds)));
const artifactVerdict = (artifact: Row): CardVerdict => {
  const verdict = text(artifact.verdict).toLowerCase();
  const confounds = Array.isArray(artifact.declared_confounds) ? artifact.declared_confounds.join(" ").toLowerCase() : "";
  return verdict.startsWith("recorded as a null") || confounds.includes("honest null") ? "null" : "descriptive";
};

export function countWord(value: number): string {
  const words = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"];
  const word = words[value] || String(value);
  return word.charAt(0).toUpperCase() + word.slice(1);
}

/** Picks the published lead fields for one artifact without re-deriving a result. */
export function selectNovelMeasurement(id: string, artifact: Row): NovelMeasurement {
  const headline = text(artifact.headline);
  const fallback = limitation(artifact);
  const results = rows(artifact.results);

  if (id === "novel_line_half_life") {
    const item = largest(results, "n_move_pairs");
    return { lead: text(item.half_life_label), leadLabel: "hours before tip", denominator: `${count(item.n_move_pairs)} move pairs`, verdict: artifactVerdict(artifact), result: sentence(headline), limitation: fallback };
  }
  if (id === "novel_live_clock_fraction") {
    const item = largest(results, "live_clock_fraction");
    return { lead: number(item.live_clock_fraction), leadLabel: "of the clock still contested", denominator: `${count(item.n_games_total)} games`, verdict: artifactVerdict(artifact), result: sentence(headline), limitation: fallback };
  }
  if (id === "novel_load_bearing_index") {
    const item = results.reduce((best, entry) => Number(record(entry.estimator_a_elo_onoff).delta_winprob) > Number(record(best.estimator_a_elo_onoff).delta_winprob) ? entry : best, results[0] || {});
    return { lead: number(record(item.estimator_a_elo_onoff).delta_winprob), leadLabel: "win-probability swing", denominator: `${count(results.length)} teams`, verdict: artifactVerdict(artifact), result: sentence(headline), limitation: fallback };
  }
  if (id === "novel_market_foresight_premium") {
    const grouped = record(artifact.results);
    const names = Object.keys(grouped);
    const name = names.reduce((best, entry) => Number(record(grouped[entry]).mfp_mean) > Number(record(grouped[best]).mfp_mean) ? entry : best, names[0] || "");
    const item = record(grouped[name]);
    return { lead: number(item.mfp_mean), leadLabel: "excess resolving power per bit", denominator: `${count(item.n_checkpoints)} in-game checkpoints`, verdict: artifactVerdict(artifact), result: sentence(headline), limitation: fallback };
  }
  if (id === "novel_overreaction_harvest_gap") {
    const item = largest(results, "ohg");
    return { lead: number(item.ohg), leadLabel: "harvest gap", denominator: `${count(item.max_disagreement_n)} max-disagreement observations`, verdict: artifactVerdict(artifact), result: sentence(headline), limitation: fallback };
  }
  if (id === "novel_schedule_fatigue_tax") {
    const item = results.reduce((best, entry) => Number(entry.sft_credible_pts_per100_ortg) < Number(best.sft_credible_pts_per100_ortg) ? entry : best, results[0] || {});
    return { lead: number(item.sft_credible_pts_per100_ortg), leadLabel: "pts per 100 ORtg, season-averaged", denominator: `${count(results.length)} team-seasons`, verdict: artifactVerdict(artifact), result: sentence(headline), limitation: fallback };
  }
  if (id === "novel_rest_asymmetry") {
    const panels = record(artifact.panels);
    const contrast = rows(panels.contrast_vs_equal_rest).find((item) => item.cell === "home +2 or more") || {};
    const base = record(panels.rest_differential);
    return { lead: number(contrast.delta_vs_equal), leadLabel: "home +2 vs equal-rest contrast", denominator: `${count(base.n_games)} NBA games`, interval: interval(contrast.ci95), verdict: artifactVerdict(artifact), result: sentence(first(artifact.verdict, headline)), limitation: fallback };
  }
  if (id === "novel_starter_rest_absorption") {
    const restBuckets = record(record(artifact.panels).rest_buckets);
    const buckets = rows(restBuckets.cells).filter((item) => ["4", "5", "6 or more"].includes(text(item.cell)));
    return { lead: buckets.map((item) => number(item.win_frequency)).join(" / "), leadLabel: "win frequency: 4 / 5 / 6+ days rest", denominator: `${count(restBuckets.n_starts)} MLB team-starts`, interval: buckets.map((item) => interval(item.ci95)).filter(Boolean).join("; "), verdict: artifactVerdict(artifact), result: sentence(first(artifact.verdict, headline)), limitation: fallback };
  }
  if (id === "novel_pitch_repeat_excess") {
    const panels = record(artifact.panels);
    const overall = rows(record(panels.overall).cells)[0] || {};
    const claims = rows(artifact.preregistered_claims).filter((item) => item.verdict === "CONTRADICTED");
    const result = claims.length ? `Two preregistered claims were contradicted: ${claims.map((item) => text(item.claim).replace(/[.!?]+$/, "")).join("; ")}.` : sentence(first(artifact.verdict, headline));
    return { lead: number(overall.excess), leadLabel: "repeat-pitch excess", denominator: `${count(overall.n_pairs)} adjacent pitch pairs`, interval: interval(overall.ci95), verdict: claims.length ? "contradicted" : "confirmed", result, limitation: fallback };
  }
  return { lead: "", leadLabel: "", denominator: "", verdict: artifactVerdict(artifact), result: sentence(headline), limitation: fallback };
}
