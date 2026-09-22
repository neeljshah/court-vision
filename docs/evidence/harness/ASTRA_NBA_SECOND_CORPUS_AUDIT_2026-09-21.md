# NBA second corpus: model-side leak audit + draft prereg outline (astra, 2026-09-21). NOTHING SCORED.

Source: codex design lane (read-only), archived verbatim by the orchestrator. Design text, not a measurement.

1. LEAK AUDIT

The S86 model is not yet suitable as a confirmatory fourth arm. Its computation is chronological, but parameter provenance, archive vintage and prior exposure remain unresolved.

Input trace: scripts/platformkit/eval_gate/s86_nba_every_tick.py:102 constructs p0 from data/domains/basketball_nba/games.parquet. It normalizes season labels, replays games before game_date, and resolves teams from market_ticker (:78). domains/basketball_nba/ratings.py:153 excludes dates on or after that date; earlier outcomes update Elo (:159-172). Constants are K=20, mean=1500, home adjustment=76 and seasonal regression=0.25 (domains/basketball_nba/elo_config.py:10).

At t, model uses only p0, score_home, score_away, period and game_clock_s (s86_nba_every_tick.py:128). scripts/platformkit/ingame/nba_checkpoint_benchmark.py:112 clips p0, converts it through the normal quantile with margin sigma=13.5, and constructs elapsed time and expected scores. scripts/platformkit/live_repricer.py:255 dispatches to domains/basketball_nba/repricer.py:57: current margin plus expected remaining margin, divided by remaining-margin standard deviation, enters the normal CDF.

Same-game fitting: CLEAN in this computation. Earlier games from the same seasons can update Elo; the evaluated game's outcome cannot. UNKNOWN for historical parameter selection: fixed constants and the description "NBA-calibrated" do not establish which seasons informed their choice (elo_config.py:3). No fitted pregame M0 is loaded; RESULTS_LEDGER_SYSTEM.md:587 reports zero valid pre-start M0 games, which does not invalidate this separate Elo prior.

Future inputs: CLEAN in the immediate formula; outcome is used only afterward for losses (s86_nba_every_tick.py:129-133). UNKNOWN end-to-end: retrospective play timestamps do not prove contemporaneous receipt or unrevised values. Furthermore, scripts/platformkit/eval_gate/s148_live_requote.py:3 documents post-final-buzzer rows carrying final scores. Those are not future relative to their timestamps, but are invalid evidence of live predictive calibration.

Join: CLEAN for S360's exact canonical (game_id, ts) join, without interpolation (scripts/platformkit/ingame/nba_checkpoints_to_joined.py:128). Upstream state-to-price pairing is backward as-of, not exact (scripts/platformkit/venue_history/nba_wallclock_join.py:79). Current code has a 300-second staleness limit; its application to the archived bytes is UNKNOWN without build provenance. S360's close_ts is the maximum observed timestamp, not verified settlement (:206, :221).

Selection: CLEAN regarding direct outcome/future-value conditioning. S86 filters traded=True, then selects alternating sorted game IDs with seed=0 (s86_nba_every_tick.py:76, :93; scripts/platformkit/foundry/tiers.py:122). No price band or informative-tick filter selects model coverage. However, traded=True is assigned to every source price observation, not measured trade freshness (scripts/platformkit/venue_history/nba_checkpoints_full.py:121).

Prior exposure prevents calling this untouched validation: RESULTS_LEDGER_SYSTEM.md:236 records S86 scoring its 797-game half; docs/evidence/harness/S86_nba_every_tick_2026-09-03.md:42 records S58 scoring all 1,593 games at one checkpoint. Conversion creates no new independent observations.

Without validated model provenance, market and tick-state comparisons remain candidates; raw-model and model-dependent blend comparisons do not. The actual MLB instrument differs from that shorthand: A=market, B=recalibrated market, C=market plus state, D=C plus model; there is no pure state-only arm (baseline_four_arm.py:100).

2. FOURTH-QUARTER WEIGHTING

Tick weighting targets the observation-frequency distribution, overweighting densely sampled fourth-quarter states and potentially post-final repetitions. Choose a period-stratified primary: equal weights of 1/4 across Q1-Q4, averaging tick losses within each game-period and then across games, with whole-game bootstrap resampling. This removes period-frequency weighting; clustering alone would only address uncertainty, and this estimand requires an explicit prospective scorer amendment.

3. DRAFT PREREG OUTLINE

Hypotheses and signs

Delta=candidate loss minus A loss; negative means lower loss. Freeze C-minus-A Brier as primary; B-minus-A, D-minus-A and D-minus-C are secondary, with D conditional on provenance clearance. No outcome-selected arm or population promotion.

Arms and features

Preserve MLB A/B/C/D definitions above, fixed ridge 1e-3 including intercept, 100 Newton steps and tolerance 1e-9; scaling and constant removal use training rows only.

The converter's state_summary emits exactly home_score, away_score, quarter, seconds_remaining (nba_checkpoints_to_joined.py:172). Derive score_diff from the scores; possession is absent. seconds_remaining means remaining regulation time in Q1-Q4 and current-period time in overtime.

Require finite probabilities, binary consistent outcomes, timezone-aware timestamps and valid declared state. Apply the live rule: exclude quarter>=4 with seconds_remaining=0. Collapse identical duplicate keys; exclude every conflicting key from all compared arms. Count all exclusions. Missing model excludes D's paired population only under an amended instrument.

Frozen inputs, folds and embargo

Pin canonical per-file SHA-256 manifest, source archives, converter, scorer and model-generation versions. All unresolved hashes and version pins: TO-FREEZE-FROM-CENSUS, with source-history verification.

One expanding fold per game's first parseable UTC tick date, including excluded ticks when assigning dates. Keep whole games together; training games must finish before test-date midnight minus three days. Preserve symmetric three-day temporal embargo and shared team/matchup purges; absent team fields make temporal protection essential. Exclude no-training warm-up folds identically across arms.

Populations, phases and reporting

Primary: period-stratified C-minus-A Brier on the frozen eligible validation population. Resample whole games, preserving their periods: 2,000 draws, seed 13, 95-percent intervals. Report log-loss, tick-weighted and equal-game summaries, state transitions, Q1-Q4 and overtime secondarily; archive keys, folds, training IDs, predictions and paired losses.

Each late-game cohort is exploratory. late_game_cohorts.py:16 currently defines only MLB/NFL and rejects NBA (:40). Its inclusive price bands [0.05,0.20] and [0.80,0.95], first eligible tick/game/band and 50-game threshold may be retained, but NBA state thresholds require prospective definition; do not silently import NFL limits. Cohort counts: TO-FREEZE-FROM-CENSUS.

Bars and stop rule

Preserve EPS=1e-6 and minimum 30 scored games. With sufficient games, interval upper bound<0 means AHEAD; lower bound>0 means BEHIND; an interval containing zero means UNDERPOWERED. MATCH has no numerical definition in the inherited gate and must not substitute for UNDERPOWERED (gate_a0_ingame_vs_market.py:84).

Maximum absolute single-game contribution divided by absolute total must be <=0.5; undefined ratios block interpretation. Stop on integrity or chronology failures; maximum two attempts. Charge one trial before metrics, record launch K and applicable family/global bars, and report min_corpora_eff at launch. MLB and NBA must support the same comparison; season splits are not additional corpora.

Scope, corpus pins and provenance

Candidate corpus: data/cache/ingame_grade_joined/nba_checkpoints_r1. Supplied census: 1,593 games, 465,249 ticks, 2024-10-22 through 2026-06-13; model present on 232,951 ticks and absent on 232,298.

Disclose historical scoring. Freeze validation-game identities only after exposure review. Existing scorer rejects the r1 directory name (baseline_four_arm_features.py:16); resolve this compatibility defect before sealing.

Pre-seal eligibility census

An amended --census-only run must freeze files/bytes, unique keys, duplicates/conflicts, exclusions by file/game/reason, live eligible ticks/games, model coverage, transitions, date folds, training sizes, warm-up and post-warm-up denominators, and period/cohort counts. Every unresolved denominator: TO-FREEZE-FROM-CENSUS.

Thirty post-warm-up games is an eligibility floor, not demonstrated statistical power. Counts alone cannot establish a detectable calibration difference. Raw corpus size does not establish a powered second corpus.

Seal

Seal only after blockers and denominators are resolved; require committed normalized-content SHA-256 verification. Do not tune thresholds, select favorable periods, impute models, use future fields, reinterpret final-state rows as live, or reuse development rows as untouched validation.

4. TICKS WITHOUT MODEL

Yes: compare model-independent arms on exactly identical eligible keys, folds and weights, regardless of model availability. Compare D only against A/B/C recomputed on the same model-present subset; never compare D's subset against another arm's full population. Existing eligibility rejects missing models for every arm (baseline_four_arm_eligibility.py:100), so this requires amendment before sealing.

5. THREE FALSE-AHEAD RISKS

1. Final-state repetition and period concentration. Guard: live-tick exclusion, fixed period weights, whole-game bootstrap and concentration checks.
2. Previously examined observations presented as fresh validation. Guard: exposure inventory, frozen development/validation identities and independent observations where needed.
3. Unverified model vintage or unequal arm populations. Guard: source/model hashes, parameter-history audit, timestamp and orientation checks, and identical paired keys.

No files were edited and no scores were computed.
