# Analytics Catalog

Every analytic this system actually computes, with its artifact path, its chart (if any), and
its honest caveat. This is a **descriptive index**, not a claims sheet: numbers here are copied
from artifacts on disk, each carries the caveat that limits it, and none is an edge/ROI/$ claim.

> **The single truth source for any number is
> [docs/JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md).** Where a figure below and the packet
> disagree, the packet wins. The product is a **calibrated** predictor -- "match or honestly
> trail the devigged close" -- not a betting-edge product. An honest REJECT or null is a
> success, not a failure.

Every showcase module lives under `scripts/platformkit/analytics_showcase/`, writes JSON to
`out/`, and (where it renders one) a PNG to `docs/img/`. Each is built to run once and be
re-checked; the numbers shown are the values on disk as of the last run.

**Corpus scale:** across all sports the system has generated 103,048 claims in 103 families;
101,865 (98.85%) fall inside a validation sample -- 101,864 verified, 0 mismatched, 1
unverifiable. That is **sidecar sample coverage** (per-family self-check at generation time),
**not** an independent full-corpus re-audit. Source: `analytics_showcase/out/claims_corpus_meta.json`.

---

## 1. Calibration and market-comparison

How close our probabilities sit to outcomes, and how that compares to the devigged market on
the same rows. In every corpus with a live market the market matches or beats us -- stated
plainly, because that is the honest verdict.

| Analytic | What it measures | Artifact | Chart | Honest caveat |
|---|---|---|---|---|
| Cross-sport scoreboard | One rating object scored OOS across NBA/MLB/soccer/tennis; per-market paired model-vs-market delta and verdict | `analytics_showcase/out/cross_sport_scoreboard.json` | `docs/img/cross_sport_scoreboard.png` | 17 rows: 13 UNDERPOWERED, 3 MODEL_SHARPER_PROVISIONAL, 1 MARKET_SHARPER_PROVISIONAL. All PROVISIONAL -- CIs wide, most underpowered. NBA end-Q1 winprob delta -0.0084 (market sharper). Composition only, every value copied from its source artifact. |
| Calibration over time | Model vs market Brier + ECE, split by calendar month | `analytics_showcase/out/calibration_over_time.json` | `docs/img/calibration_over_time.png` | Only 2 months exist in the corpus (2026-06, 2026-07) -- a 2-point trend, not a drift study. Market beats model on Brier + ECE in both months; gap widens (MLB) / model degrades faster (soccer). |
| Market-disagreement profile | Rows bucketed by `\|model_prob - market_prob\|`; per-bucket model vs market Brier and `model_closer_rate` | `analytics_showcase/out/market_disagreement_profile.json` | `docs/img/market_disagreement_profile.png` | At the biggest disagreements the market is usually right: MLB model closer 37.7% (n=33,402), soccer 21.5% (n=4,406). This is a market-efficiency confirmation, not a contrarian edge. |
| Reliability diagram (model vs market) | Static reliability/sharpness curve on the shared OOS bins | rendered from the decomposition bins | `docs/img/reliability_model_vs_market.png` | Visual companion to the Murphy decomposition; same corpus, same caveats. |
| Win-prob walk-forward folds | Per-fold leak-free walk-forward Brier for the NBA in-game win-prob model | `docs/img/winprob_walkforward_folds.png` | (chart) | Walk-forward, leak-free after the Q4-feature removal; see the retraction story for the leak that was caught. |
| NBA in-game Brier vs market | End-of-quarter model Brier against the devigged in-game market | `docs/img/nba_ingame_brier_vs_market.png` | (chart) | See [ingame-conditioning](evidence/ingame-conditioning.md). Provisional n; verdicts honest incl. market-sharper. |
| Soccer calibration pack | Murphy model-vs-market decomposition + ECE by minute-bucket + Brier by disagreement-bucket for soccer_intl | `analytics_showcase/out/soccer_calibration_pack.json` | `docs/img/soccer_calibration_pack.png` | soccer_intl corpus: n=9003 rows -- far smaller than mlb/nba, wider CIs, single-fold reads not durable. Murphy: model Brier 0.2279 vs market 0.1427 (gap=+0.0852); market leads. Minute-bucket ECE (weighted): 0.3580. At the biggest disagreements (>=.10, n=4406) model closer only 21.5%. `edge_claimed: false`. |
| Statcast coverage (MLB framing inputs) | 2025 statcast pitch corpus: pitch-type mix, velo spread, and framing-metric input completeness | `analytics_showcase/out/statcast_showcase.json` | `docs/img/statcast_showcase.png` | DESCRIPTIVE coverage only -- **no** predictive/edge claim of its own. 693,037 pitches, 19 pitch types (FF 31.8%, SI 15.5%, SL 14.3%); framing-ingredient columns 99.6-100% non-null. Cites the framing `PREDICTIVE_VERIFIED` receipt as context (rho 0.418 vs 0.272 baseline, 8 folds, 7 sign-holding) **without recomputing it**, preserving that receipt's corpus-deviation caveat (built on `savant_full__2023/2024`, not `statcast_fuller`, which lacks a `description` column). |

Evidence pages: [calibration-decomposition](evidence/calibration-decomposition.md) -
[devig-stack](evidence/devig-stack.md) - [ingame-conditioning](evidence/ingame-conditioning.md).

---

## 2. Decomposition and error anatomy

Breaking a single Brier number into its parts so the failure modes are visible instead of
averaged away.

| Analytic | What it measures | Artifact | Chart | Honest caveat |
|---|---|---|---|---|
| Murphy decomposition | 10-bin `Brier = reliability - resolution + uncertainty` for model and market | `analytics_showcase/out/murphy_decomposition.json` | (bins feed the reliability chart) | MLB model Brier 0.2377 (rel 0.0127, res 0.0236, n=78,986); soccer 0.2279 (rel 0.0928, res 0.0382). Good reliability is not an edge -- the market's resolution still leads. |
| State-conditioned calibration | ECE bucketed by model-prob band x game-state time bucket; ranks the worst buckets as the improvement backlog | `analytics_showcase/out/state_conditioned_calibration.json` | `docs/img/state_calibration_heatmap.png` | MLB n-weighted ECE: model 0.079 vs market 0.0591 (market better). 26,340 MLB records skipped for missing state field. This is a backlog map, not a claim of conditional advantage. |
| Residual anatomy | Segments graded in-game records by inning/half x prob band; total absolute-residual mass per segment | `analytics_showcase/out/residual_anatomy.json` | `docs/img/residual_anatomy.png` | Error concentrates in MLB early innings (1-3) at prob .4-.6: mean abs residual 0.4912 over n=12,344, ~2.4x the next-worst segment. Diagnostic only. |

Evidence page: [calibration-decomposition](evidence/calibration-decomposition.md).

---

## 3. Execution quality

Whether a probability would have survived contact with a real price. The honest headline is
that realized CLV is **null** wherever no independent closing feed was captured -- we do not
paper over the gap.

| Analytic | What it measures | Artifact | Chart | Honest caveat |
|---|---|---|---|---|
| Paper execution audit | Paper-bet ledger: placement divergence `\|model_prob - implied_prob(price)\|`, fill/suppress split, settled outcomes | `analytics_showcase/out/paper_execution_audit.json` (+ `.md`) | -- | Units are probability points, **not dollars**. n=83 records; divergence median 0.092 pp -- a pre-trade sizing input, not realized CLV. `realized_clv_pct` is **null** for all 37 settled rows: no independent closing-price feed captured on this channel. |
| Market microstructure measurement | Kalshi quote cadence, price-move size, model-vs-market divergence, overround from the rescued pod backup | `analytics_showcase/out/tick_microstructure.json` | `docs/img/tick_microstructure.png` | MEASUREMENT (latency/cadence), **not a trading signal**. MLB Kalshi total-market: median inter-tick gap 35s (mean 80s, p90 170s); median `\|dprob\|` 0.02 (p90 0.09); model-vs-market divergence median 0.116 (p90 0.225) -- annotated as calibration-gap, **not edge**. WNBA capture cadence median 88s; overround median 0.01 (p90 0.03). Thin data: single-day-ish backup, **no NBA coverage** -- a snapshot measurement, not a durable multi-day corpus. |

Evidence page: [devig-stack](evidence/devig-stack.md). See also the Shin devig endpoint
`POST /api/devig` and the correlation-aware Kelly sizing (`kelly_corr`).

---

## 4. Knowledge validation and self-refutation

The strongest signal in the repo is the self-refutation trail: we publish more nulls than
confirms, and keep a running graveyard of rejected signals.

| Analytic | What it measures | Artifact | Chart | Honest caveat |
|---|---|---|---|---|
| Honesty exhibit | Per-sport validation-ledger tally: confirmed / null / not-testable / failed-replication | `analytics_showcase/out/honesty_exhibit.json` | `docs/img/honesty_exhibit.png` | Nulls (351) outnumber confirms (168) 2.1x across sports. The interaction-factory ledger alone is 239 nulls vs 38 confirms (n=1,003). Publishing nulls is the point. |
| Reject graveyard | Every SHIP/REJECT/DEFER verdict from the leak-free gate | `analytics_showcase/out/reject_graveyard.json` | `docs/img/reject_graveyard.png` | 804 total verdict rows; 68 distinct (sport, signal) currently on a REJECT-family verdict; 627 REJECT vs 95 SHIP. A REJECT is honest market-efficiency evidence, not a failure. |
| Claims-corpus scale | Per-family generated-claim volume with validation-sidecar coverage across all sports | `analytics_showcase/out/claims_corpus_meta.json` | `docs/img/claims_corpus_meta.png` | 103 claim families, 103,048 generated claims; 99/103 families carry a `*_validation.json` sidecar. 101,865 claims (98.85%) fell inside a validation sample -- 101,864 verified, 0 mismatched, 1 unverifiable. This is **sidecar sample coverage** (per-family self-check at generation time), **not** an independent full-corpus re-audit. Volume split: NBA 62,227 / MLB 21,519 / tennis 13,709 / soccer 4,275 largest. Freshest family file 3 days stale. Bookkeeping, not a new proof. |
| Answer-engine QA coverage | Fail-closed answer engine measured on its own QA regression + coverage-stress banks | `analytics_showcase/out/qa_coverage_stats.json` | `docs/img/qa_coverage_stats.png` | QA regression bank 87/87 pass (fail-closed -- a correct no_data/not_supported/ambiguous counts as PASS). Coverage-stress: honest coverage 36.6% (316/863 answerable-expected resolved) across 1,307 rows; per-sport ok-rate soccer 19% to tennis 42%. The rest are deliberate refusals (missing corpora / unsupported combos / 125 pure `edge_language` refusals at 100% refused), not silent wrong answers. Read from `data/cache/analytics_verify/` artifacts (as_of 07-18/07-19); no engine re-run. |
| Tennis gate receipts | Two REAL preregistered tennis gate verdicts: pregame-prior cross-corpus (ATP<->WTA) + in-game surface-context detail | `analytics_showcase/out/tennis_showcase.json` | `docs/img/tennis_showcase.png` | CALIBRATION only (held-out Brier / Diebold-Mariano) -- never a market edge or $ claim; vs_close UNPROVEN. Pregame cross-corpus prior: **REPLICATED** both directions (ATP-train/WTA-test Brier 0.1698->0.1597 n=40516 test states; WTA-train/ATP-test 0.155->0.1432 n=14559; DM clustered by game_id). Surface-specific hold prior: **REJECT** -- does not beat surface-blind on either tour (ATP pooled delta +0.000121, WTA +0.002492, both wrong-signed); planted-null control correctly dies. An honest REJECT is a success. |

Evidence pages: [retraction-story](evidence/retraction-story.md) -
[leak-instruments](evidence/leak-instruments.md).

---

## 5. Build provenance

Who wrote the system, and at what cadence. Descriptive git facts, no performance claim.

| Analytic | What it measures | Artifact | Chart | Honest caveat |
|---|---|---|---|---|
| Agent-fleet history | Commit volume/cadence over the build; agent-authored and Claude-co-authored share | `analytics_showcase/out/agent_fleet_history.json` | `docs/img/agent_fleet_history.png` | 3,224 commits Mar-Jul 2026, 95.75% agent-authored, 67.9% Claude-co-authored. Volume metric only -- commit count is not a quality metric. |

Evidence page: [agent-fleet-direction](evidence/agent-fleet-direction.md).

---

## 6. CV / tracking coverage

What the broadcast computer-vision pipeline has actually produced. Volume and coverage only --
tracking-quality (MOT) metrics are unbenchmarked, so no accuracy claim is made.

| Analytic | What it measures | Artifact | Chart | Honest caveat |
|---|---|---|---|---|
| CV tracking stats | Rows / games / players / feature-names produced by the CV feature pipeline | `analytics_showcase/out/cv_tracking_stats.json` | `docs/img/cv_tracking_stats.png` | 17,254 rows, 241 games, 252 players, 29 feature names. Volume/coverage only -- MOT accuracy unbenchmarked (JOB_EVIDENCE_PACKET s4). No date/season breakdown (no date column; box-score join returns 0 rows). |

Evidence page: [cv-pipeline](evidence/cv-pipeline.md).

---

## 7. Player-intelligence coverage

What the intelligence layer covers, and -- critically -- which branded advanced metrics can and
**cannot** be honestly reproduced from the inputs on hand.

| Analytic | What it measures | Artifact | Chart | Honest caveat |
|---|---|---|---|---|
| Player-metric landscape | Raw input-column coverage mapped to which value-metric families are supportable | `analytics_showcase/out/player_metric_landscape.json` | `docs/img/player_metric_landscape.png` | 77,744 rows, 807 players, 3 seasons, 0% box-column missing. "Supported" means the raw inputs exist, never that a branded metric is reproduced. Box-only value index is APPROX -- **not** BPM/EPM (no RAPM target to fit). On-off is unadjusted, a biased precursor to RAPM. |
| Box-only value index | Per-36 linear box value index, Win-Score/Berri (2006) convention, frozen weights | `analytics_showcase/out/box_value_index.json` | `docs/img/box_value_index.png` | 501/807 players over 750-min floor; weights declared once, not tuned to output. Top 10 is the expected 2023-26 MVP-tier cluster (face-valid). **NOT** RAPM/EPM/DARKO/LEBRON/BPM -- box counting stats only, blk/stl the sole defensive ingredients. Diacritic-split player ids fragment some rows (upstream join bug, unfixed). DESCRIPTIVE_ONLY. |
| On/off net-rating differential | `net_rating_on_per48 - net_rating_off_per48` per player-season | `analytics_showcase/out/on_off_showcase.json` | `docs/img/on_off_showcase.png` | 2024-25 top Jokic +23.713 (n_ranked 353, median +0.195); 2025-26 top Wembanyama +17.043 (n_ranked 350, median +0.127). ROSTER CONFOUND on every row: not a causal impact estimate; who shares the floor is uncontrolled. Unadjusted precursor to RAPM. DESCRIPTIVE_ONLY. |
| Aging curve (honest refusal) | Whether an age curve is buildable from the data on hand | `analytics_showcase/out/aging_curve_lite.json` | (none -- refusal) | Verdict `not_buildable`: no birthdate/age column in any `data/domains/basketball_nba/` parquet, only 3 season snapshots. Returns the refusal instead of a fabricated curve; matches the landscape audit's `aging_curve: not_supported`. |
| Dossier completeness | Per-category fill rate across the player-report corpus | `analytics_showcase/out/dossier_completeness.json` | `docs/img/dossier_completeness.png` | 1,249 dossiers, 28 categories, median completeness 0.464. Coverage varies widely (rebounding 0.95, pace-fit 0.01) -- a completeness map, not a quality score. |

For the full RAPM-family reasoning and the do-not-fake metric list, see the public evidence
page [evidence/industry-metrics.md](evidence/industry-metrics.md), the underlying
[research/INDUSTRY_ANALYTICS_NBA.md](../jobsearch/research/INDUSTRY_ANALYTICS_NBA.md) *(local
only)*, and the packet.

---

## 8. Frontier measurements

The newest measurements, built on the corpora already on disk and kept deliberately exploratory.
Each is a calibration, market-absorption, or measurement-hygiene readout -- no edge, no ROI, no
dollar figure -- and each carries an explicit **novelty verdict** naming its closest prior work
and how ours differs. None is claimed as first-ever.

| Analytic | What it measures | Artifact | Chart | Honest caveat |
|---|---|---|---|---|
| Market information-arrival curve | Per-checkpoint (MLB inning / soccer 5-min bucket) Brier for our model vs the live market vs a naive score-diff-only logistic baseline, plus `market_minus_model_brier` (negative = market beats model), leak-free against actual outcomes | `analytics_showcase/out/info_arrival_curve.json` | `docs/img/info_arrival_curve.png` | The market is ahead of our in-game model at essentially every checkpoint in both sports and the gap WIDENS late: MLB `market_minus_model_brier` -0.015 (inning 1) -> -0.090 (inning 9); soccer -0.112 (kickoff) -> -0.189 (85'). Straight confirmation the live market absorbs game state faster than our model -- calibration-gap measurement, no edge. **Novelty: INCREMENTAL** -- same contract-minute model/market/outcome instrument as arXiv 2606.07811 (Jun 2026; 409k NBA rows, 0.64-for-one absorption), applied to the MLB/soccer corpora we hold with a naive baseline added; not first-ever. |
| Lead x time-remaining calibration atlas | NBA in-game reliability map reshaped into a 2D lead-band x time-remaining grid: per bucket model vs market mean prob vs realized `outcome_rate`, behind a preregistered `can_price` gate (n_games>=30 AND model_n>=10 AND \|model-outcome\|<=0.06) | `analytics_showcase/out/comeback_atlas.json` | `docs/img/comeback_atlas.png` | 84 state buckets, 7 masked (n_games<30). Tick-weighted, not game-weighted (stated, not hidden). Worst unmasked model-vs-market gaps are the overtime buckets -- `lead_+01_05\|ot` -0.265, `lead_-05_10\|ot` +0.156 -- where the model is mispriced vs market. MARKET = Polymarket in-play price off our own `nba_checkpoints_full.parquet`. Calibration atlas, `edge_claimed: false`. **Novelty: INCREMENTAL** -- reshapes the same three-way (model, market, outcome) join as arXiv 2606.07811 into a lead x time atlas off our held corpus; not first-ever. |
| Market over/underreaction spectrum | Consecutive-row market price moves bucketed by \|delta\| into 5 magnitude buckets; per bucket the mean moved-to price vs mean subsequent `outcome_rate` (`moved_to_minus_outcome`; + = overshoot, - = undershoot) | `analytics_showcase/out/market_overreaction.json` | `docs/img/market_overreaction.png` | MLB `moved_to_minus_outcome` is flat-positive +0.052..+0.080 across all bucket sizes (n 794-66,697); soccer_intl flat-negative -0.19..-0.36, worsening in the larger (thin: n 21-7,791) buckets. This is a directional-bias check, NOT the Choi & Hui over/underreaction "spectrum" (no moderate-underreaction / extreme-overreaction flip shows up in either sport); it conflates market bias with our win-prob/vig convention -- a clean test would need de-vigged prices. **Novelty: INCREMENTAL** -- Moskowitz (2021) magnitude-bucketed move-vs-outcome test + Choi & Hui (2014) in-play soccer version, here at consecutive-row grain on the corpora we hold; not first-ever. |
| Hypothesis survival rate | Share of TESTABLE hypotheses across the 4-sport validation ledgers whose latest verdict is CONFIRMED/REPLICATED, sliced by sport and keyword-bucketed category | `analytics_showcase/out/mechanism_survival.json` | `docs/img/mechanism_survival.png` | 287 rows, 256 testable (31 not-testable, 10.8%); overall survival 50.4% (129/256). By sport: NBA 56.0% (42/75), tennis 54.6% (24/44), soccer 51.8% (29/56), MLB 39.7% (31/78). Half of all testable mechanisms fail to confirm -- a NULL/REJECT is honest market-efficiency evidence, not a failure. (A stray 3-row `nba` label distinct from `basketball_nba`, all 3 confirmed, is left as-is.) `edge_claimed: false`. **Novelty: N/A** -- internal measurement-hygiene scoreboard over our own ledger, not a market-facing method; no borrowed novelty claim. |
| Cross-sport calibration-transfer table | Murphy reliability/resolution composed across NBA/MLB/soccer/tennis, comparability-gated so CRPS never shares an axis with Brier; only the Brier reliability component is treated as cross-sport-comparable | `analytics_showcase/out/kernel_transfer.json` | `docs/img/kernel_transfer.png` | Only 2 of 4 sports have a market-side Murphy reliability component: MLB moneyline model 0.0127 vs market 0.0061, soccer_intl 0.0928 vs 0.0534 -- both show the model less reliable than market, magnitude differs ~5.9x. n=2 sports is a same-direction coincidence to re-check if a 3rd sport gets a market-side decomposition, not a general pattern. CRPS (MLB totals/margin), Brier-only (NBA), and no-market tennis gates are verdict text only, never coerced onto the reliability axis. `edge_claimed: false`. **Novelty: ALREADY_DONE_ON_CORE_METHOD** -- the reliability/resolution/uncertainty split is classical Murphy (1973); this adds only a comparability-gated cross-sport composition (no new decomposition math), unverified against literature for that composition; not first-ever. |

These carry no dedicated evidence page yet; every number is copied from the artifact on disk and
the truth source remains [JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md).

---

## Do not claim

These are documented **measurement artifacts**. They appear in this repo only inside explicit
retraction framing (see [JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md) and
[.claude/rules/no-edge-claims.md](../.claude/rules/no-edge-claims.md)), never as a current
result of any analytic catalogued above:

- the retracted pregame-ROI headline (a market-follow artifact; the model's own number is
  break-even-minus-vig)
- the retracted end-of-Q3 win-prob Brier (a Q4 feature leak; the leak-free walk-forward number
  is ~0.141)
- the retracted in-play "edge" / in-play accuracy figures (an L5-proxy ceiling, not realized)
- any other figure on the packet's retraction list

No analytic in this catalog produces a dollar, ROI, bankroll, or profit figure. Accuracy is not
edge; the market is efficient; we match or honestly trail the close.

---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](INDEX.md) - [Home](../README.md) - [Glossary](GLOSSARY.md) - [Evidence packet](JOB_EVIDENCE_PACKET.md)
