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
| MLB velo bands (in-season drift) | League release-speed distribution two ways: velo-band shares per pitch type (fixed 3-mph bands) and monthly median velo per pitch type across the 2025 season | `analytics_showcase/out/mlb_velo_bands.json` | `docs/img/mlb_velo_bands.png` | DESCRIPTIVE_ONLY -- a distribution/coverage exhibit, **no** predictive or edge claim; in-season ramp-up is a known physical effect reported as-is. 690,490 classified pitches of 693,037 raw. Floors: band-share n>=500/pitch type, monthly drift cell n>=200, chart = top-6 by count. Thin edge-of-season months (Mar/Oct) fall below the cell floor and are dropped, not smoothed. |
| MLB count-leverage mix + outcome proxies | Pitch-type mix and per-pitch outcome proxies (type S/B/X share, in-zone share) by count-leverage class: behind/even/ahead partition + two_strike/three_ball overlapping lenses | `analytics_showcase/out/mlb_count_leverage.json` | `docs/img/mlb_count_leverage.png` | DESCRIPTIVE_ONLY, no market/ROI/$ claim. 693,037 of 693,037 pitches carry a valid count. CORPUS LIMIT: `type`==S conflates called+swinging+foul (no swing/take column). Floors: class n>=500; chart top-5 pitch types (FF/SI/SL/CH/ST). two_strike/three_ball OVERLAP the partition (not additive). Behind-class strike(S) share 49.8%, in-zone 58.6% -- full mix-shift table in JSON. |
| Brier Skill Score (vs climatology, vs market) | Standard BSS = 1 - Brier/Brier_ref per sport x in-game checkpoint, against a constant-climatology base rate and the devigged market | `analytics_showcase/out/brier_skill_scores.json` | `docs/img/brier_skill_scores.png` | DESCRIPTIVE_ONLY, `edge_claimed: false`. Honest headline: BSS(model vs market) sits near/below 0 in both sports (mlb [-0.46,-0.08], soccer_intl [-1.08,-0.47]) -- the model does NOT beat the market, and that null is the point. BSS(model vs climatology) is strongly positive in mlb ([+0.01,+0.14]) but mixed in soccer_intl ([-1.25,-0.30]) -- expected/not an edge either way. Floors: n>=30 rows/grain. Single-fold Jun-Jul 2026 corpus, no CIs. |
| Reliability-bin bootstrap CIs (model vs market) | 95% cluster-bootstrap (resample `game_id`, n_boot=1000) CI on every 10-bin reliability point + the calibration gap, flagging which bins are real miscalibration vs within-noise | `analytics_showcase/out/calibration_stability.json` | `docs/img/calibration_stability.png` | DESCRIPTIVE_ONLY, `edge_claimed: false`. Game-clustered (not row-level) bootstrap on purpose -- deliberately conservative given within-game autocorrelation. mlb: model 4/10 eligible bins significant vs market 0/10; soccer_intl: model 8/10 vs market 6/10 (n=78,986/227 games mlb; 9,003/51 games soccer_intl). **Novelty: ALREADY_DONE_ON_CORE_METHOD** -- classical cluster bootstrap (Efron) + CI'd reliability diagrams, applied here, not first-ever. |
| Market convergence (gap + entropy over game time) | Two OUTCOME-FREE properties of the forecast pair per checkpoint: disagreement gap `mean\|model_prob-market_prob\|` and predictive sharpness (Bernoulli entropy, bits) for market + model | `analytics_showcase/out/market_convergence.json` | `docs/img/market_convergence.png` | DESCRIPTIVE_ONLY, `edge_claimed: false` -- ignores outcome entirely, a forecast-agreement/uncertainty view. Floors: n>=30 rows/checkpoint. mlb (10 checkpoints): gap 0.070->0.279 (widens), market entropy 0.967->0.876 bits. soccer_intl (10 checkpoints): gap 0.155->0.106 (narrows), market entropy 0.821->0.439 bits. Entropy collapse late-game is expected, reported as context not a finding. **Novelty: STANDARD_INSTRUMENT** -- textbook forecaster-agreement + entropy-decay measures, application only. |
| Calibration by market type | For each LABELED market type with resolved outcomes (MLB moneyline, soccer match result): n + model/market Brier + 10-bin ECE. For the UNLABELED type (MLB totals, rescued Kalshi quote-tracks, no outcome): n + model-vs-market divergence only, Brier disclosed null | `analytics_showcase/out/calibration_by_market_type.json` | `docs/img/calibration_by_market_type.png` | DESCRIPTIVE_ONLY, `edge_claimed: false`. mlb_moneyline model Brier 0.2377 vs market 0.2067 (n=78,986); soccer_match model 0.2279 vs market 0.1427 (n=9,003); mlb_total UNSCORED (n=2,113 rows / 21 quote-tracks, divergence median 0.116, no resolved outcome -- disclosed not fabricated). Floors: n>=30/type; `mlb_clean` byte-dup excluded. |
| MLB pitch-sequencing transition matrices | Within-plate-appearance P(next pitch type \| previous), one matrix per count-leverage class (unconditional `all` + behind/even/ahead + two_strike/three_ball overlapping lenses), over the top-8 league pitch types | `analytics_showcase/out/pitch_sequencing.json` | `docs/img/pitch_sequencing.png` | DESCRIPTIVE_ONLY, `edge_claimed: false`, no market/ROI/$ claim -- pitch pairs already thrown, not a Markov predictor. 512,289 transitions from 690,493 classified pitches of 693,037 raw. Strict adjacency (pitch_number diff==1, same PA/pitcher) -- mid-PA pitching changes sever pairs, never bridge. `all`-class matrix coverage 95.5%. Floors: ROW_MIN_N=200/prev-type row, CLASS_MIN_TRANS=2000/class. |

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
| Within-game residual autocorrelation | Lag-1 sample autocorrelation of each game's model/market residual series (`r_t = prob_t - terminal outcome`); distribution of that per-game autocorr across games | `analytics_showcase/out/residual_autocorrelation.json` | `docs/img/residual_autocorrelation.png` | High positive autocorr is EXPECTED (outcome is terminal-constant, path is smooth) -- the real point is a variance caveat: within-game rows are far from independent, so per-row Brier/count CIs OVERSTATE effective sample size. mlb: median model 0.981 vs market 0.980 (n=222/225 games, share>=0.9 95.5%/96.4%); soccer_intl: median model 0.962 vs market 0.949 (n=51/51 games, share>=0.9 82.4%/80.4%). Floors: n>=10 rows/game, residual variance>1e-9 (flat paths skipped, never scored 0). `edge_claimed: false`. |

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
| Soccer form-vs-strength rank stability | Cross-lens rank concordance for soccer_intl national teams: tie-corrected Spearman rho + Pearson r between trailing-10 form win-rate and net-xG EW strength, over shared above-floor teams | `analytics_showcase/out/soccer_form_stability.json` | `docs/img/soccer_form_stability.png` | DESCRIPTIVE_ONLY, `edge_claimed: false`. A parallel-forms convergent-validity read, **NOT** a temporal split-half and **NOT** a predictor (soccer_intl predictive gate is closed upstream). Requested `temporal_split_half` reported `NOT_AVAILABLE_IN_STORE` (each claim store holds one as-of snapshot) -- names the fields a re-ingest would need rather than faking a split. Spearman rho=0.6419, Pearson r=0.6369 over n=153 shared teams (26 form-only, 0 strength-only); form win-rate is quantized to 0.1 (tie_fraction 0.935), tie-corrected average-rank Spearman used. Floors: inherited n_matches>=200, MIN_OVERLAP=30. |

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
| NBA team-vs-team scoring grid | Mean total points and mean point margin (row minus column) for every team pairing, pooled across box-score seasons | `analytics_showcase/out/nba_matchup_grid.json` | `docs/img/nba_matchup_grid.png` | DESCRIPTIVE_ONLY -- describes games already played, **not** a forecast. 3,611 two-team games (0 dropped) across 3 seasons (2023-24..2025-26), 30 teams. Mask: pairing reported only at n_meetings>=2 -- 870/870 kept, 0 masked. `mean_margin` pools home+away (no venue flag at this grain), opponent-raw. Highest-scoring pairing ATL-IND (255.7 total); lowest CHA-POR (197.0). |
| NBA player consistency profiles | Game-to-game dispersion of per-36 pts/reb/ast as a shrunk coefficient of variation per player; composite = unweighted mean of the three (lower = steadier) | `analytics_showcase/out/nba_consistency_profiles.json` | `docs/img/nba_consistency_profiles.png` | DESCRIPTIVE_ONLY -- past variance, **not** skill/value, **not** predictive. Floors: >=10 min/game to enter the per-36 series, >=15 qualifying games, shrink_k=20 games. 579 players over floor across 3 seasons. Composite-CV median 0.6235 (min 0.3448, max 0.8849). Steadiest: Luka Doncic, Nikola Jokic, Domantas Sabonis; streakiest: P.J. Tucker, Cam Reddish, Gary Harris. CV is not on the same scale across archetypes (mechanically inflates for low-mean stats). |
| NBA player form curves | Per-player 10-game rolling per-36 box composite (frozen `WEIGHTS_PER36`, Berri 2006 convention), league percentile bands, and biggest first-vs-last-window net movers | `analytics_showcase/out/nba_form_curves.json` | `docs/img/nba_form_curves.png` | DESCRIPTIVE_ONLY -- a trajectory, **not** a live hot/cold signal. Floors: >=8 min/game to enter a window, window total_min>=120, >=20 qualifying games. 562 eligible movers of 807 players, 3 seasons, 61,298 pooled windows. League percentile bands p10=8.95 .. p90=20.11. Top riser Victor Wembanyama (+19.82, 18.05->37.87, now 100th pctile). **NOT** BPM/EPM/RAPM/DARKO -- box counting stats only. |
| NBA home/away split anatomy | Home vs away split of the player box scores: league-level per-stat home-minus-away means (raw + relative %) by season/pooled + shooting-pct deltas, and the cross-player distribution of home-minus-away scoring with top deviators both directions | `analytics_showcase/out/home_away_anatomy.json` | `docs/img/home_away_anatomy.png` | DESCRIPTIVE_ONLY, `edge_claimed: false` -- games already played, **not** a home-court betting edge. Venue = the VERIFIED `is_home` flag (0/1), same column `player_box_splits.py` groups on. Pooled per-player-game pts home bump +0.081 pts (+0.75%), well below the ~2-3pt TEAM home-court margin -- unweighted, not minutes/pace/rest/opponent adjusted. Shooting: FG +0.65pp, FG3 +0.77pp, FT +0.77pp home. 74,450 valid rows of 77,744 raw (3,294 dropped invalid venue/id), 543 players over the 15-games-each-side floor; median player delta +0.039, 51.6% score more at home. Biggest home booster Ace Bailey (+3.81 ppg); biggest road booster Kon Knueppel (-3.81 ppg). |
| Tennis surface-split transfer | Per-player clay<->hard win-rate gap (`clay_wr - hard_wr`) and grass adaptability (`grass_wr - ov_wr`), floored distribution + top/bottom-5 leans, per tour x window | `analytics_showcase/out/tennis_surface_transfer.json` | `docs/img/tennis_surface_transfer.png` | DESCRIPTIVE_ONLY -- matches already played, **no** market/ROI/$ edge; opponent-strength NOT controlled (a gap partly reflects scheduling/seeding). Floors copied verbatim from the producer (clay_n/hard_n>=25, grass_n>=15). ATP career (only combo with data -- WTA snapshots absent locally): clay-hard gap n=184, mean +0.016, p50 +0.015, 58.2% clay-favoring; most clay-favoring Luciano Darderi (+0.460), most hard-favoring Marius Copil (-0.310). Grass adaptability n=153, p50 +0.017, most adaptive Ramkumar Ramanathan (+0.294). WTA combos honestly report gap_n=0/adapt_n=0 (local snapshot absent, not fabricated). |
| NBA schedule-density profiles (b2b / 3-in-4 / 4-in-6) | Per-team-season frequency of back-to-back / 3-in-4 / 4-in-6 games, plus raw pooled per-36 box-composite production gap vs rested games under each (frozen `WEIGHTS_PER36`) | `analytics_showcase/out/schedule_density.json` | `docs/img/schedule_density.png` | DESCRIPTIVE_ONLY, `edge_claimed: false` -- a descriptive COMPANION to the CONFIRMED_LOCAL `b2b_rest_penalty` receipt (-1.73 pts/100 team ORtg, n=4,732, p=0.0056, `domains/basketball_nba/knowledge/validation_ledger.jsonl`), NOT a re-measurement -- runs no significance test, does not restate the receipt's number as its own. Classes OVERLAP (not additive). 90 team-seasons reported, 67,750 pooled player-games (40,157 rested baseline) across 3 seasons. Raw per-36 composite delta vs rested: b2b -0.315 (n=12,000), 3-in-4 -0.217 (n=17,531), 4-in-6 -0.193 (n=20,120) -- descriptive direction matches the receipt's tested sign but is not itself significance-tested. |
| NBA league parity / competitiveness indices | Season competitiveness from game outcomes: win-share Gini + HHI (with 1/N balanced floor) + games-normalized win_pct_stdev, plus absolute-margin dispersion and close-game rate | `analytics_showcase/out/league_parity_index.json` | `docs/img/league_parity_index.png` | DESCRIPTIVE_ONLY, `not_a_forecast: true` -- seasons already played. Same team-game derivation as the matchup grid: 3,611 two-team games (0 dropped) across 3 seasons, data through 2026-04-12; all 3 seasons meet the 200-game floor. Win-share Gini: 2023-24 0.177 (most balanced) -> 2025-26 0.2004 (least balanced). Pooled games include any playoff games in the parquet (inflates concentration, no game-type flag to split); opponent-raw, no strength-of-schedule adjustment. |
| NBA late-game per-36 shift (HONEST REFUSAL) | Intended: late-game (Q4+OT) vs full-game per-36 rate shifts per player. Actual: probes the boxscores schema and refuses -- names the fields a re-ingest would need | `analytics_showcase/out/clutch_context.json` (`status: not_buildable`) | none (by design) | HONEST-REFUSAL exhibit, same spirit as the reject graveyard -- the point is the discipline, not a number. `player_boxscores.parquet` is FULL-GAME aggregate (26 columns, no period/clutch grain) because `ingest_boxscores.py` SUMS the per-quarter cache into one row per player-game; the period grain exists upstream in `data/cache/quarter_box/<gid>_q<p>.json` but is discarded at ingest. Module fails closed rather than fabricating a split off full-game totals. Run status confirmed `not_buildable`. |

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

| Blowout dynamics (point of no return) | For each game, the earliest game-clock tick from which the score margin stays >= a threshold to the end; reported per sport x margin threshold as median game-clock and median fraction-of-game-elapsed, plus decided-game share | `analytics_showcase/out/blowout_dynamics.json` | `docs/img/blowout_dynamics.png` | DESCRIPTIVE_ONLY, `edge_claimed: false` -- reads only the score path (`state_summary`), never model/market prob, so NOT a forecast/calibration claim. mlb (178 games): a 2-run gap becomes permanent by median inning 6.0 in 75.3% of games; a 5-run gap by inning 7.5 in only 27.0%. soccer_intl (29 games): a 1-goal gap becomes permanent by median minute 39.5 in 48.3% of games (only threshold clearing the 10-game floor; 2+ goal thresholds masked, n_games_decided<10). Floors: >=10 ticks/game, >=10 decided games/cell. **Novelty: INCREMENTAL** -- descriptive clinch-time measurement (cf. Bill James safe-lead heuristic); not first-ever. |

These carry no dedicated evidence page yet; every number is copied from the artifact on disk and
the truth source remains [JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md).

---

## 9. Card atlases (descriptive entity cards)

One PNG per entity, gated by a declared sample floor and stamped `DESCRIPTIVE_ONLY` -- box-score /
rate / calibration readouts, never a projection or edge. 1,549 cards across 7 packs, built by 6
factory modules on the shared `analytics_showcase/atlas_factory.py` (each manifest carries
`descriptive_only: true` and an `n_entries` count; counts below are verbatim from those manifests
and equal the on-disk PNG count). Full gallery + reproduce: [ATLAS](ATLAS.md).

| Analytic | What it measures | Artifact | Chart | Honest caveat |
|---|---|---|---|---|
| NBA player atlas | Per-36 pts/reb/ast by season + career FG/3P/FT% shooting splits, one card per qualified player | `analytics_showcase/out/atlas_nba_manifest.json` | `docs/img/atlas/nba/` (482 PNGs) | DESCRIPTIVE_ONLY. 482/807 players over the declared career-minutes>=800 floor; box-score rates only, no projection, **not** BPM/EPM/RAPM. Diacritic-split player ids fragment a few rows (upstream join, unfixed). |
| NBA team atlas | Points/gm composition (2P/3P/FT), a box-score pace proxy/gm, and top-5 minutes leaders' PRA/36, one card per team | `analytics_showcase/out/atlas_nba_teams_manifest.json` | `docs/img/atlas/nba_teams/` (30 PNGs) | DESCRIPTIVE_ONLY. All 30 teams (each >=200 team-games across 3 seasons). Pace is a single-side box-score proxy (`FGA-OREB+TOV+0.44*FTA`), not tracked possessions. |
| MLB pitch atlas | Velocity percentiles, count-state usage, and ball/strike/in-play outcome mix, by pitch type, pitching staff, and count | `analytics_showcase/out/atlas_mlb_pitch_manifest.json` | `docs/img/atlas/mlb_pitch/` (61 PNGs) | DESCRIPTIVE_ONLY, 2025 Statcast (as_of 2025-09-28). 19 pitch types + 30 staffs + 12 counts. No per-pitch swing/miss column in this pull -> outcome mix substitutes for whiff rate; smallest type n=7 shown for completeness. |
| MLB batter atlas | Velocity/pitch-type seen, rulebook-zone rate, and exit-velo / estimated-wOBA-on-contact, one card per qualified batter | `analytics_showcase/out/atlas_mlb_batters_manifest.json` | `docs/img/atlas/mlb_batters/` (485 PNGs) | DESCRIPTIVE_ONLY, 2025 Statcast. 485/671 batters over the pitches-faced>=300 floor. Contact-panel n is batted balls; no launch-angle/whiff column in this pull, so no barrel profile or whiff rate. |
| Calibration atlas | Model-vs-market ECE by game-time checkpoint, and realized mean-outcome by prob-band x time bucket, for MLB + international soccer | `analytics_showcase/out/atlas_calibration_manifest.json` | `docs/img/atlas/calibration/` (26 PNGs) | DESCRIPTIVE_ONLY calibration readout, n>=30/card declared floor. Market ECE beats model at most checkpoints (e.g. MLB inning 1: model 0.1329 vs market 0.0903) -- stated plainly, a backlog map, not an edge. |
| Tennis + soccer atlas | Tennis: career/recent surface win-rates + clay-minus-hard skew + grass adaptation per ATP player. Soccer: trailing-10 ppg/GF/GA/GD/win-rate/clean-sheet per club | `analytics_showcase/out/atlas_tennis_manifest.json` + `analytics_showcase/out/atlas_soccer_manifest.json` | `docs/img/atlas/tennis/` (278) + `docs/img/atlas/soccer/` (187) | DESCRIPTIVE_ONLY. Per-metric sample floors; a metric below floor shows `n/a`, never fabricated. Tennis is ATP singles only in this build; soccer is trailing-10 as-of corpus end, not live form. |

Gallery + reproduce commands: [ATLAS](ATLAS.md). Served at query time by the fail-closed MCP
`atlas_card` resolver (`scripts/platformkit/answers/atlas_resolver.py`), which returns
`descriptive_only: true` and `edge_claimed: false` on every hit.

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
