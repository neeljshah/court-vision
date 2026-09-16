import { snapshot } from "./labHelpers";
import type { Sport } from "./dashboardTypes";

export type Finding = {
  slug: string;
  title: string;
  dek: string;
  sport: Sport;
  artifactIds: string[];
  asOf: string | null;
};

type ArtifactHeader = { as_of?: string | null; generated_at?: string | null };
const publishedAsOf = (id: string): string | null => {
  try {
    const artifact = snapshot<ArtifactHeader>(id);
    return artifact.as_of || artifact.generated_at || null;
  } catch {
    return null;
  }
};

const define = (slug: string, title: string, dek: string, sport: Sport, artifactIds: string[], fallbackAsOf?: string): Finding => ({
  slug, title, dek, sport, artifactIds,
  asOf: artifactIds.map(publishedAsOf).find(Boolean) || fallbackAsOf || null,
});

export const findingsIndex: Finding[] = [
  define("retraction", "Retractions", "The six numbers we took back, with what was wrong and the published correction.", "all", [], "2026-07-23"),
  define("effective-sample-size", "Effective sample size", "Why repeated within-game rows carry less independent information than their count suggests.", "mlb", ["ess_ledger"]),
  define("verdict-flips", "Verdict flips", "Claim families that changed verdict as more data arrived, in sequence.", "all", ["verdict_flip_anatomy"]),
  define("mlb-leaderboards", "MLB leaderboards, with the nulls", "Descriptive Statcast leaderboards published beside the gate nulls that did not hold.", "mlb", ["mlb_descriptive_leaderboards"]),
  define("tennis", "Tennis: momentum's grain limit", "Point-to-point momentum, game-grain nulls, and measured altitude and travel effects.", "tennis", ["tennis_grain_and_myths"]),
  define("nba-momentum", "NBA momentum, tested", "Structural context findings beside individual carryover shapes that returned null.", "nba", ["nba_momentum_tested"]),
  define("q4-shift", "The fourth-quarter shift", "Descriptive per-player Q4 versus earlier-quarter rate shifts, with their confounds stated.", "nba", ["nba_q4_shift"]),
  define("shrinkage", "When the leaderboard regresses", "Published empirical-Bayes movement from raw rates toward their group mean.", "mlb", ["mlb_shrinkage"]),
  define("reliability", "Are our probabilities honest?", "Reliability diagrams and Murphy decomposition, including the observed information gap.", "all", ["murphy_decomposition"]),
  define("forecast-life", "The life of a forecast", "Observed pre-game information arrival and in-game score checkpoints.", "all", ["novel_line_half_life", "info_arrival_curve"]),
  define("soccer-home-advantage", "Home advantage, decomposed", "International matches split on the observed neutral-site flag.", "soccer", ["soccer_home_advantage"]),
  define("bookmaker-accuracy", "We graded the bookmakers", "Proportional-devig Brier measurements on shared-game subsets.", "all", ["bookmaker_accuracy"]),
  define("rim-deterrence", "Who bends the shot chart", "A transparent NBA on/off rim-deterrence leaderboard with its roster confound.", "nba", ["rim_deterrence"]),
  define("league-parity", "How competitive is each season?", "A three-season NBA win-share concentration ledger with scope caveats.", "nba", ["league_parity_index"]),
  define("lineup-synergy", "Greater than the sum of their parts", "A five-man residual ledger published with its small-minutes limitation.", "nba", ["lineup_synergy"]),
  define("favorite-longshot", "Is the market calibrated?", "A favorite-longshot audit of observed market calibration by sport.", "all", ["market_favorite_longshot"]),
];
