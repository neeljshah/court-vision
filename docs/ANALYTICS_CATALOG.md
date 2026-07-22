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
| Dossier completeness | Per-category fill rate across the player-report corpus | `analytics_showcase/out/dossier_completeness.json` | `docs/img/dossier_completeness.png` | 1,249 dossiers, 28 categories, median completeness 0.464. Coverage varies widely (rebounding 0.95, pace-fit 0.01) -- a completeness map, not a quality score. |

For the full RAPM-family reasoning and the do-not-fake metric list, see
[research/INDUSTRY_ANALYTICS_NBA.md](../jobsearch/research/INDUSTRY_ANALYTICS_NBA.md) *(local
only)* and the packet.

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
