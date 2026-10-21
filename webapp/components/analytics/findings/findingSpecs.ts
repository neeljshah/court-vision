// findingSpecs.ts -- the T4 finding-page spec, one entry per finding (DESIGN_PRINCIPLES section 3).
// DATA module: static text plus small readers over the page's own artifact. Every count, as-of and
// verdict is read from the artifact at build time; the text here never retypes a published number.
// Verdict slots take only packet labels (lib/packetVerdicts); artifact words outside that set are
// dropped, and a finding with none renders "no packet verdict" rather than inventing one.
type R = Record<string, any>;

export type FindingSpec = {
  title: string;
  claim: string;
  /** Showcase artifact id; source + reproduce default from it. */
  artifactId: string;
  source?: string;
  reproduce?: string;
  verdicts?: (a: R) => unknown[];
  n: (a: R) => string;
  interval?: string;
  test: { gate: string; corpora: string | ((a: R) => string); folds: string | ((a: R) => string) };
  replication: string | ((a: R) => string);
  inspector?: { href: string; label: string };
  limitations: [string, string, string, ...string[]];
};

const fmt = (v: unknown) => (typeof v === "number" ? v.toLocaleString("en-US") : String(v ?? "not published"));
const sum = (xs: unknown[] = []) => xs.reduce<number>((t, x) => t + (typeof x === "number" ? x : 0), 0);
const claims = (a: R): R[] => ((a.groups ?? a.stories ?? []) as R[]).flatMap((g) => (g.claims ?? []) as R[]);
const corporaOf = (a: R) => [...new Set(claims(a).map((c) => c.corpus).filter(Boolean))].join("; ") || "not recorded";
const replicated = (a: R) => {
  const r = claims(a).filter((c) => c.verdict === "REPLICATED").length;
  return r ? `${r} of ${claims(a).length} claims carry REPLICATED (two disjoint slices); the rest are single corpus.` : "single corpus";
};
const SINGLE = "single corpus";

export const FINDING_SPECS: Record<string, FindingSpec> = {
  "bookmaker-accuracy": {
    title: "How accurate were the market sources?",
    claim: "The market sources are close, not ranked. On shared games the tennis match-winner and soccer over/under 2.5 sources sit within a few ten-thousandths of a Brier point of each other. This is a descriptive comparison, not a test.",
    artifactId: "bookmaker_accuracy",
    n: (a) => `${fmt(a.sports?.tennis?.n_shared)} tennis + ${fmt(a.sports?.soccer?.n_shared)} soccer shared games`,
    test: { gate: "descriptive: proportional-devig Brier per source on each source's shared-game subset; no gate", corpora: "tennis odds and soccer odds parquets (one per sport)", folds: "none (full window, no split)" },
    replication: SINGLE,
    limitations: [
      "Sample and independence: rows are games priced by several sources; the sources share games, so their scores are not independent draws.",
      "Scope: two markets (tennis match winner, soccer over/under 2.5) over the stated observation windows only.",
      "Does not establish which source is sharper in general, or which posts a line first; it measures accuracy at the captured timestamps.",
    ],
  },
  "effective-sample-size": {
    title: "Effective sample size: rows are not games",
    claim: "Row counts overstate the evidence. Consecutive in-game rows are near-duplicates, so the historical corpora carry far less independent information than their row counts suggest.",
    artifactId: "ess_ledger",
    source: "webapp/public/data/showcase/ess_ledger.json",
    n: (a) => ((a.corpora ?? []) as R[]).map((c) => `${fmt(c.n_rows)} rows / ${fmt(c.n_games)} games`).join("; "),
    test: { gate: "descriptive: AR(1) effective sample size from committed lag-1 residual autocorrelation", corpora: (a) => ((a.corpora ?? []) as R[]).map((c) => c.sport ?? c.name ?? "corpus").join(", ") || "not recorded", folds: "none" },
    replication: SINGLE,
    inspector: { href: "/analytics/observation-dependence/", label: "observation-dependence inspector" },
    limitations: [
      "Sample and independence: the ledger's subject is dependence itself; the distinct-game count is the conservative anchor and the AR(1) figure is a model.",
      "Scope: the historical joined corpus (revision 1); the segment-clean recomposition has not been published yet.",
      "Does not establish an interval-width correction for any published figure.",
    ],
  },
  "favorite-longshot": {
    title: "A favorite-longshot audit of the market",
    claim: "This grades the market, not the model. Published prices show a mild favorite-longshot pattern in tennis and no systematic pattern in MLB across the published probability bins.",
    artifactId: "market_favorite_longshot",
    n: (a) => `${fmt(a.sports?.tennis?.n_total)} tennis + ${fmt(a.sports?.mlb?.n_total)} MLB source records`,
    interval: "nominal 95% Wilson interval per bin (coverage not established)",
    test: { gate: "descriptive: realized frequency against implied probability per bin; grades the market, not our model", corpora: "tennis and MLB market snapshots (one per sport)", folds: "none" },
    replication: SINGLE,
    limitations: [
      "Sample and independence: rows are records, not proven-independent games; the Wilson intervals assume independence and their 95% coverage is not established.",
      "Scope: two sports, the published bins only; a few MLB records fall outside the bins.",
      "Does not establish that the market is efficient or inefficient in general, and says nothing about our model.",
    ],
  },
  "forecast-life": {
    title: "The life of a forecast",
    claim: "Descriptive only. Published prices absorb information gradually before a game and step with the score during it. This page traces both curves and tests nothing.",
    artifactId: "novel_line_half_life",
    n: (a) => `${fmt(sum(((a.results ?? []) as R[]).map((r) => r.n_move_pairs)))} pre-game move pairs across ${fmt((a.results ?? []).length)} results`,
    test: { gate: "descriptive: line half-life and in-game information-arrival checkpoints; no gate", corpora: (a) => `daily line history ${fmt(a.observation_window?.start)} to ${fmt(a.observation_window?.end)} (${fmt((a.source_artifacts ?? []).join(", "))}); segmented in-game grade corpus`, folds: "none" },
    replication: SINGLE,
    limitations: [
      "Sample and independence: move pairs and checkpoint rows repeat within games, so the counts overstate independent information.",
      "Scope: the sports and windows in the two source artifacts; late checkpoints have very few rows.",
      "Does not establish how fast any single market reacts, or that a model can anticipate the moves.",
    ],
  },
  "ingame-join-integrity": {
    title: "MLB in-game join integrity",
    claim: "A data defect, found and fixed, not a model gain. Part of the MLB in-game corpus had joined ticks from consecutive-day games under one outcome label. The corpus was re-segmented and the affected calibration artifacts were regenerated, so every number that moved is a population change.",
    artifactId: "mlb-ingame-integrity",
    source: "webapp/public/data/audits/mlb-ingame-integrity.json",
    reproduce: "python scripts/platformkit/check_ingame_join_integrity.py",
    n: (a) => `${fmt(a.per_sport?.mlb?.ticks)} MLB ticks, ${fmt(a.per_sport?.soccer_intl?.ticks)} soccer ticks`,
    test: { gate: "integrity audit: per-file game segmentation and tick-level label agreement", corpora: "MLB and international soccer in-game tick corpora", folds: "none (full-corpus audit)" },
    replication: "audit of two sport corpora; not a replicated effect",
    inspector: { href: "/analytics/state-reliability/", label: "state reliability inspector" },
    limitations: [
      "Sample and independence: ticks repeat within games; counts are ticks, not games.",
      "Scope: MLB and international soccer in-game corpora; NBA and tennis rows stay clear.",
      "Does not establish that the regenerated artifacts improve the forecaster; the changes are population changes.",
    ],
  },
  "league-parity": {
    title: "How competitive is each NBA season?",
    claim: "Descriptive only. Win-share concentration differs across the covered NBA seasons, and the ledger reports how balanced each one was. It does not say why.",
    artifactId: "league_parity_index",
    n: (a) => `${fmt((a.seasons ?? []).length)} seasons, ${fmt(sum(((a.seasons ?? []) as R[]).map((s) => s.n_games)))} games`,
    test: { gate: "descriptive: season-level concentration index with declared game floors", corpora: "NBA game results by season", folds: "none" },
    replication: SINGLE,
    limitations: [
      "Sample and independence: one value per season, so the season-to-season comparison rests on very few points.",
      "Scope: the covered NBA seasons; an in-progress season is partial against the declared floor.",
      "Does not establish why parity moved, or that the trend continues.",
    ],
  },
  "lineup-synergy": {
    title: "Lineup synergy: a five-man residual ledger",
    claim: "Small minutes, so read with care. Some five-man NBA lineups score above or below the sum of their players' individual ratings. The minutes behind each lineup are small, and the residual is not shown to persist.",
    artifactId: "lineup_synergy",
    n: (a) => `${fmt(a.n_qualified)} qualified lineups, ${fmt(a.season)}`,
    test: { gate: "descriptive: lineup residual against summed individual ratings, minimum-minutes floor", corpora: (a) => `NBA stints, ${fmt(a.season)}`, folds: "none" },
    replication: SINGLE,
    limitations: [
      "Sample and independence: small minutes per lineup; possessions within a lineup are not independent.",
      "Scope: one NBA season, lineups above the floor only.",
      "Does not establish that a lineup's residual persists or is caused by the combination.",
    ],
  },
  "mlb-leaderboards": {
    title: "MLB leaderboards, with the nulls attached",
    claim: "The one gated signal failed. Catcher, platoon and umpire leaderboards are descriptive. The umpire-tendency signal for game totals was gated against a planted null and did not pass.",
    artifactId: "mlb_descriptive_leaderboards",
    verdicts: (a) => [a.umpire_totals_gate?.verdict],
    n: (a) => `${fmt(a.umpire_totals_gate?.n_umpires)} umpires in the gate; ${fmt(a.catcher_ooz?.n_qualified)} qualified catchers`,
    test: {
      gate: "leak-free expanding gate with a planted null (shuffled umpire assignment) for the totals signal; leaderboards ungated",
      corpora: (a) => `Statcast ${fmt(a.observation_window?.seasons)}`,
      folds: (a) => `${fmt((a.umpire_totals_gate?.fold_rmse_deltas ?? []).length)} walk-forward folds`,
    },
    replication: SINGLE,
    limitations: [
      "Sample and independence: pitches cluster within games and umpires; the leaderboards carry no intervals.",
      "Scope: one Statcast window; the park-factor ranking was too sparse to publish.",
      "Does not establish any umpire or catcher effect on game outcomes; the gated totals signal failed.",
    ],
  },
  "nba-momentum": {
    title: "NBA momentum, tested",
    claim: "Structure held, streaks did not. Fatigue, rest and clutch effects held in tested NBA hypotheses. Individual game-to-game carryover shapes came back null.",
    artifactId: "nba_momentum_tested",
    verdicts: (a) => claims(a).map((c) => c.verdict),
    n: (a) => `${fmt(claims(a).length)} tested claims; per-claim n in the tables`,
    test: { gate: "leak-free effect test against an internal baseline (forward-claim scoreboard)", corpora: corporaOf, folds: "per claim, as recorded in the scoreboard" },
    replication: replicated,
    inspector: { href: "/analytics/the-loop/", label: "forward-claim loop" },
    limitations: [
      "Sample and independence: player-game rows repeat players and games; per-claim n counts rows.",
      "Scope: NBA box-score and stint corpora for the recorded seasons.",
      "Does not establish a market-relative effect; a NULL means no measurable signal past the baseline, not that streaks never occur.",
    ],
  },
  "q4-shift": {
    title: "Fourth-quarter rate shifts and their limits",
    claim: "Descriptive splits, not a skill. Per-player fourth-quarter rate shifts are shown with their confounds stated. They are not a late-game skill and not a prediction.",
    artifactId: "nba_q4_shift",
    n: (a) => `${fmt(a.n_qualified)} qualified of ${fmt(a.n_considered)} players, ${fmt(a.observation_window?.n_games)} games`,
    test: { gate: "descriptive: Q4 versus Q1-Q3 per-36 rates with an appearance floor", corpora: (a) => `local per-quarter boxes, ${fmt(a.observation_window?.seasons)}`, folds: "none" },
    replication: SINGLE,
    limitations: [
      "Sample and independence: quarters repeat players and games; per-36 rates from few Q4 minutes are noisy.",
      "Scope: the seasons present in the local cache, players above the floor only.",
      "Does not establish clutch skill or predict future fourth quarters.",
    ],
  },
  reliability: {
    title: "Reliability decomposition and its closure check",
    claim: "Read the components only after the closure check. The direct Brier score and the published ten-bin reconstruction do not close exactly. The reliability, resolution and uncertainty components are shown beside that remainder.",
    artifactId: "murphy_decomposition",
    source: "webapp/public/data/showcase/murphy_decomposition.json",
    n: (a) => `${fmt(a.sports?.mlb?.n_rows)} MLB rows, ${fmt(a.sports?.soccer_intl?.n_rows)} soccer rows`,
    test: { gate: "descriptive: Murphy decomposition with a ten-bin reconstruction remainder", corpora: (a) => fmt(a.corpus), folds: "none" },
    replication: SINGLE,
    inspector: { href: "/analytics/calibration/", label: "Calibration inspector (bins and checkpoints)" },
    limitations: [
      "Sample and independence: in-game rows repeat within games; counts are rows, not games.",
      "Scope: MLB and international soccer in-game corpora.",
      "Does not establish the cause of the model-to-reference score gap.",
    ],
  },
  "rim-deterrence": {
    title: "Rim deterrence: an on/off leaderboard",
    claim: "A leaderboard with its confound attached. The on/off rim-deterrence table describes shot charts. It does not isolate one defender's effect, because roster context confounds every value.",
    artifactId: "rim_deterrence",
    n: (a) => ((a.seasons ?? []) as R[]).map((s) => `${fmt(s.n_qualified)} qualified players (${fmt(s.season)})`).join("; "),
    test: { gate: "descriptive: on/off rim-attempt share with a minutes floor", corpora: "NBA on/off zone data for the listed seasons", folds: "none" },
    replication: SINGLE,
    limitations: [
      "Sample and independence: on/off splits share teammates and opponents, so players are not independent.",
      "Scope: the listed NBA seasons, players above the floor.",
      "Does not establish a causal deterrence effect; roster context confounds every value.",
    ],
  },
  shrinkage: {
    title: "When the leaderboard regresses to the mean",
    claim: "A regularized estimate, not a skill ranking. Empirical-Bayes shrinkage moves raw MLB rates toward their group mean, and the shrunk table depends on the fitted prior.",
    artifactId: "mlb_shrinkage",
    n: (a) => ((a.groups ?? []) as R[]).map((g) => `${fmt(g.n_entities)} ${g.key ?? "rows"}`).join("; "),
    test: { gate: "descriptive: empirical-Bayes shrinkage under a fitted prior", corpora: (a) => `Statcast ${fmt(a.observation_window?.seasons)}`, folds: "none" },
    replication: SINGLE,
    limitations: [
      "Sample and independence: pitches cluster within games; catcher rows are source rows, not verified distinct people.",
      "Scope: one fixed 2022-2023 Statcast slice.",
      "Does not establish a skill ranking; the shrunk value depends on the modeling prior.",
    ],
  },
  "soccer-home-advantage": {
    title: "Home advantage in international football",
    claim: "Held in a local test, not yet replicated. International teams at a true home venue win more and score more than at neutral venues. The split held in a local leak-free test and has not been replicated on an independent corpus.",
    artifactId: "soccer_home_advantage",
    verdicts: (a) => [a.receipt?.verdict],
    n: (a) => `${fmt(a.observation_window?.n_matches_played)} matches`,
    test: { gate: "local leak-free mechanism test (mechanism ledger), including a split-half-by-era check", corpora: (a) => fmt(a.source_parquet), folds: "split halves by era" },
    replication: "single corpus (CONFIRMED_LOCAL: not replicated on an independent corpus)",
    limitations: [
      "Sample and independence: matches repeat teams and tournaments; the neutral flag is as recorded in the source.",
      "Scope: international results only, across the full recorded window.",
      "Does not establish why the gap grew or the size of home advantage in club football.",
    ],
  },
  tennis: {
    title: "Tennis momentum: real at the point, gone at the game",
    claim: "Momentum is measurable point to point and disappears at the game grain. Two tiebreak myths are null.",
    artifactId: "tennis_grain_and_myths",
    verdicts: (a) => claims(a).map((c) => c.verdict),
    n: (a) => `${fmt(claims(a).length)} tested claims; per-claim n in the tables`,
    test: { gate: "leak-free effect test against an internal baseline (forward-claim scoreboard)", corpora: corporaOf, folds: "per claim; some checked on split halves" },
    replication: replicated,
    inspector: { href: "/analytics/the-loop/", label: "forward-claim loop" },
    limitations: [
      "Sample and independence: points repeat within matches; the large point-level n is not n independent events.",
      "Scope: the slam point corpora and match corpora named in each claim.",
      "Does not establish a market-relative effect; a NULL means no measurable signal past the baseline.",
    ],
  },
  "verdict-flips": {
    title: "Verdict flips: when a claim changed status",
    claim: "Several claim families changed verdict as more data arrived. Each change is listed in sequence from the forward-claim scoreboard, and the current status is the last entry.",
    artifactId: "verdict_flip_anatomy",
    n: (a) => `${fmt(a.summary?.n_families)} claim families, ${fmt(a.dating_coverage?.n_history_rows_total)} history rows`,
    test: { gate: "descriptive: verdict history per claim family ordered by run time", corpora: "forward-claim scoreboard", folds: "none" },
    replication: "not applicable (a history of re-tests)",
    inspector: { href: "/analytics/the-loop/", label: "forward-claim loop" },
    limitations: [
      "Sample and independence: families share corpora, so flips are not independent events.",
      "Scope: only history rows with a run timestamp can be dated.",
      "Does not establish which verdict is final; the current status is the last entry.",
    ],
  },
};
