# In-game gap map -- PREMISE VERIFICATION (L1-L20), 2026-09-03

Read-only lane. Verifies the premise of every lever in
`docs/evidence/harness/INGAME_GAP_MAP_2026-09-03.md` against the code and data actually on
disk at HEAD 277bfa90b. Nothing was charged, no prereg sealed, `data/registry/` and
`data/cache/eval_gate/backtest_fwer.jsonl` were never opened for write. Calibration language
only. Every number below was produced by a read this session unless it cites an artifact.

Format per lever: (1) what exists (module + function, read on disk) -- (2) ever scored
leak-free on ticks vs the in-play line (artifact + numbers, or NEVER) -- (3) the data it needs
and whether it is present (path, n rows, n games, range, columns) -- (4) one-line verdict --
(5) the exact bar for a lane.

## Standing facts this lane re-measured (they recur below)

- The canonical SCORED tick store is `data/cache/ingame_grade_joined/mlb`: **78,986 rows /
  227 games / 2026-06-20..2026-07-12**, columns `sport, game_id, ts, model_prob, market_prob,
  side, state_summary, outcome, close_source, close_prob, close_ts, edge_claimed`. Inter-tick
  gap p50 31.0 s / p90 82.0 s. The screened subset every S06/S43/S58 trial uses is 47,104
  ticks / 158 games.
- The wider capture store `data/cache/ingame_grade/mlb` is 79,566 rows / 401 games /
  2026-06-19..2026-09-01, 396 games carrying `settled`+`home_win`. It additionally carries
  `xg_*`, `spread_bp`, `book_thinness`, `stale_quote`, `espn_wp` on 25,585 rows and
  `mlb_batter_id`/`mlb_pitcher_id`/`mlb_pitcher_pitch_count`/`mlb_ondeck_id`/
  `mlb_bullpen_used` on 11,251 rows -- the close-join drops all of them.
- Incumbent: `gap_blend_arm` (e4) leak-free game-first-date Brier **0.206786** vs market
  **0.195387**, raw_model 0.236683, on 47,104 ticks / 158 games (`S43_ingame_max_loser_wp`,
  `S06_stacker_result`). ESS ICC 0.32-0.37, design effect 97.5-112.1, **n_eff 420-483** of
  47,104.

---

## L1 -- in-game STATE features screened in the factory

1. **Exists.** `scripts/platformkit/ingame/ingame_baseout_mlb.py:109 baseout_summary_fields`
   writes `outs`, `base` (3-bit mask), `bos` (base-out state 0-23), `re` (a fixed published
   RE24 lookup, `_RE24` at :30), `count` into each tick's `state_summary`; capture also adds
   `pitch_count` and `tto`. The only consumer today is
   `scripts/platformkit/eval_gate/stacker.py:47 inning_bucket`, which parses **inning and
   nothing else**. The frozen FWER partition additionally holds 11 feature-grid families
   sourced from `data/cache/ingame/*.parquet` labelled `(live_tick, inplay)`.
2. **Scored leak-free on ticks vs the line: NEVER.** `grep` over `docs/evidence/` for
   `baseout|base_out|RE24|run_expectancy` returns only the gap map and the FWER spec; there is
   no result line in `RESULTS_LEDGER_SYSTEM.md`. The 11 in-game feature-grid families are
   scored against `p0` (a pregame baseline column), not against an in-play line.
3. **Data: PRESENT, unparsed.** In `ingame_grade_joined/mlb` (78,986 rows) the
   `state_summary` string carries `outs`/`base`/`bos`/`re`/`count` on **52,546 rows
   (66.53 pct)** and `pitch_count`/`tto` on **43,989 rows (55.69 pct)**; `inning` on 52,646
   (66.65 pct). Separately `data/cache/ingame/mlb_pitch_states__{2022..2026}.parquet`
   (66,266 / 69,823 / 70,326 / 65,983 / 29,319 rows, 25 cols, 2026 file = 100 games
   2026-03-25..2026-06-16) carries `count_balls, count_strikes, runners, outs,
   atbat_pitch_number, pitch_type, pitch_velocity, sp_pitch_count_prior,
   velo_decline_vs_early, base_run_value, leverage_bucket` -- but with `p0` and `outcome`,
   **no market column**.
4. **Verdict: BUILDABLE NOW.** The state is already on two thirds of the scored ticks; only
   the parser and the screen are missing. (S82 is the running lane on the factory side.)
5. **Bar:** a state-signal e4 variant, fit inside the folds on the SCREEN partition only,
   improving paired Brier by **>= +0.004 vs e4 0.206786** on the 47,104-tick set with a
   game-clustered DM CI excluding 0. Report n_eff, not n.

## L2 -- player / lineup grain at the tick

1. **Exists.** `scripts/platformkit/eval_gate/s80_player_grain_screen.py` (268 lines) -- the
   lane landed this session.
2. **Scored: YES, screen side, SCREEN_NULL.** `docs/evidence/harness/S80_player_grain_2026-09-03.md`:
   headline (embargo 1d) 2,267 ticks / 13 games, incumbent 0.248462 vs candidate 0.244703,
   market 0.244971, improvement **+0.003759** (below the +0.004 bar), DM CI
   [-0.026879, +0.034398], 13 clusters; companion (embargo 0d) 3,717 ticks / 23 games,
   improvement **-0.005770**, CI [-0.012984, +0.001445]. No prereg drafted, ledger untouched.
3. **Data: PRESENT but thin.** Player identity on 11,251 of 79,566 `ingame_grade/mlb` ticks
   (S80 measured 8,384 / 10.53 pct at its HEAD); the scored store has **zero** player columns
   (the close-join drops them), so the identity must be re-joined on `(game_id, ts)` --
   8,309 scored ticks over 53 games survive, 2026-07-09..2026-07-12. **0.00 pct** of NBA,
   soccer, tennis, wnba ticks carry player state.
4. **Verdict: ALREADY DONE (screen), and what replaces it is a CAPTURE gap.**
5. **Bar:** not a modelling lane any more. The next bar is capture: player identity on
   >= 60 pct of MLB ticks across >= 2 disjoint windows before re-screening, and the close-join
   must stop dropping the five columns.

## L3 -- structural prior (Markov base-out / possession chain as a model probability)

1. **Exists, partially, and not as a probability.** `ingame_baseout_mlb.py` is a **parser plus
   a constant RE24 table** -- `parse_baseout` :72 returns state, `_RE24` is fixed league
   averages, explicitly "not fit on our data". There is **no transition matrix and no
   win-probability output**. `src/sim/rest_of_game_sim.py:266 RestOfGameSim.simulate` is a
   basketball possession Monte Carlo (`EmpiricalPossessionModel` :217, `_poss_remaining` :276,
   `_ot_poss` :406) returning `home_win_prob`, `margin_mean`, `total_mean` and the full
   `home_final_samples` arrays. It reads a leak-free NBA state row from
   `src.ingame.state_featurizer.featurize_game`. It is under `src/**` -- a human-gated path.
2. **Scored on ticks vs the line: NEVER for base-out.** For the possession sim, the only
   in-game scoring is `scripts/platformkit/benchmarks/crps_market/last_run_ingame_mlb.json`
   (margin CRPS at inning checkpoints, n 20-26 per checkpoint, every verdict UNDERPOWERED --
   see L20). No artifact scores either against a tick line.
3. **Data: PRESENT for MLB base-out** (52,546 scored ticks carry `bos`, above); **PRESENT for
   NBA possessions** (`data/cache/ingame/possession_states_{2024_25,2025_26}.parquet`, 30,383
   and 30,199 rows, 1,313 games 2025-10-21..2026-05-24, columns `seconds_remaining,
   frac_elapsed, home_margin, possessions_elapsed, pace_so_far, run_diff,
   poss_since_lead_change, outcome`) -- but the NBA possession corpus carries no market column.
4. **Verdict: BUILDABLE NOW for the MLB base-out prior; BLOCKED for the possession sim**
   (its state featurizer and the sim itself are `src/**` human-gated, and its NBA state corpus
   has no line).
5. **Bar:** a base-out transition prior fit strictly on prior dates, emitted as a probability
   at every tick carrying `bos`, blended by the incumbent guard -- **>= +0.004 vs e4 0.206786**
   on the 52,546-tick covered slice, with e4 re-scored on the SAME slice as the comparison
   (the S58-trial-1 rule: never compare a slice candidate to the 47,104-tick figure).

## L4 -- corpus size (backfill in-play prices)

1. **Exists.** `scripts/platformkit/venue_history/kalshi_intragame.py` --
   `list_settled_markets_page` :69 hits `GET {base}/markets?series_ticker=&status=settled`,
   `fetch_market_candles` :143 hits
   `GET {base}/series/{s}/markets/{t}/candlesticks?start_ts&end_ts&period_interval=1` on
   `https://api.elections.kalshi.com/trade-api/v2`. **Keyless public GET** (`http_cache.py`
   sends only Accept + User-Agent). 1-minute candles, `MAX_CANDLES_PER_CALL = 5000` (a
   server cap verified live), one ~83 h window per market, `min_close_ts` is a server no-op.
   `odds_provider/inplay_history.py` is the same two venues with `period_interval` as a
   parameter and Polymarket `clob.polymarket.com/prices-history`; it writes only where the
   caller points. `venue_history/build_price_series.py` consolidates
   `data/venue_history/**.jsonl` into `data/cache/inplay_odds/<sport>_price_series.parquet`.
2. **Scored: N/A (this is corpus, not a model).** No per-run backfill result artifact was ever
   written to `docs/` -- the only on-disk record of extent is 23 `_progress.json` sidecars
   under `data/venue_history/`.
3. **Data: MUCH LARGER THAN THE SCREENS USE.** `data/cache/inplay_odds/` holds **29,221,912
   price-series rows** over 8 sports, columns `sport, venue, game_date, ticker_or_slug,
   event_key, market_type, side, ts, prob, traded, close_time, result_where_known`:

   | file | rows | events | date range | outcome known |
   |---|---|---|---|---|
   | mlb | 13,473,591 | 3,932 | 2023-03-30..2026-07-09 | 3,920 (99.7 pct) |
   | nba | 8,399,632 | 1,835 | 2023-02-23..2026-06-14 | 1,823 (99.0 pct) |
   | soccer_intl | 2,261,903 | 288 | 2026-06-11..2026-07-07 | 288 |
   | tennis | 1,854,100 | 986 | 2026-05-24..2026-07-08 | 986 |
   | kbo | 1,414,315 | 558 | 2026-05-13..2026-07-08 | 558 |
   | wnba | 967,102 | 287 | 2026-05-21..2026-07-09 | 287 |
   | npb | 646,834 | 298 | 2026-05-05..2026-07-08 | 298 |
   | soccer | 204,435 | 36 | 2026-05-03..2026-05-24 | 36 |

   **MLB moneyline with a known outcome: 12,772,159 rows / 3,780 events.** That is ~24x the
   158 games the screens run on. What is missing on those rows is not the line and not the
   outcome -- it is a **model/state series**. Ceiling: the Kalshi half is all 2026 (earliest
   `_progress.json` close 2026-04-27; 2025 settled events return `"markets": []`, so no
   candlesticks) -- `LICENCE_mlb_close_history.md:83-96`. The 2023 tail is Polymarket-only.
   Also present: `data/cache/inplay_odds/nba_checkpoints_full.parquet` --
   **465,249 rows / 1,593 games / 2024-10-22..2026-06-13**, columns `game_id, game_date, ts,
   period, game_clock_s, score_home, score_away, margin, market_prob, traded, market_ticker,
   outcome_home_win, venue`, **0 outcome nulls**, median 276 ticks/game. This is a complete
   state x line x outcome tick corpus, ten times the MLB screened corpus, already on disk.
   Live-capture stores are near-empty by retention: `data/cache/inplay_history/` = 4 dated
   jsonl / 76,901 rows / one date (2026-07-27); `data/cache/ingame_shadow_history/` = 34 files
   / 24,612 rows / 2026-07-05..07-27 (mlb, tennis, wnba only).
4. **Verdict: DATA PRESENT -- the x10 corpus does not need a backfill, it needs a model side.**
5. **Bar:** the register bar ("n_games x10 with a joined outcome + tick line") is **already met
   on disk for NBA (1,593 games)**. The lane bar becomes: a leak-free model series produced at
   every one of the 465,249 NBA ticks and scored against `market_prob`, with the DM CI
   clustered on game and both corpus units (2024-25 / 2025-26) reported.

## L5 -- tick quality (duplicates, held positions, ESS)

1. **Exists.** `scripts/platformkit/ingame/quote_freshness.py:83 freshness_mask` (row FRESH iff
   `market_prob` differs from the previous row by > 1e-9), `filter_fresh` :110,
   `freshness_share` :118, `longest_stale_run` :135; `inplay_tick_latency.py` for cadence;
   `gap_effective_n.effective_sample_size` for ICC / design effect / n_eff. Nothing in the e4
   / S58 scoring path calls any of them -- every arm scores raw ticks.
2. **Scored: partially.** ESS is reported per trial (S43 ICC 0.3248/0.3614/0.3738, deff
   97.5/108.4/112.1, n_eff 483.03/434.66/420.36 on 47,104 ticks; S06 differential ICC 0.5311,
   deff 158.81, n_eff 296.6; S58-1 ICC 0.3198, n_eff 467.3). **Duplicate and held-tick share
   have NEVER been reported.**
3. **Data: measured this session on `data/cache/ingame_grade_joined/mlb`** (78,986 rows /
   227 games, the largest scored tick corpus):
   - duplicate `(game_id, ts)` rows: **1,659 (2.10 pct)**
   - `market_prob` identical to the previous tick: **59,045 / 78,759 (74.97 pct)**
   - `model_prob` identical to the previous tick: **72,232 / 78,759 (91.71 pct)**
   - `state_summary` identical to the previous tick: 34,848 / 78,759 (44.25 pct)
   - **BOTH model and market held (a fully redundant tick): 55,022 / 78,759 = 69.86 pct.
     Informative ticks = 23,964 (30.34 pct).**
   - distinct `model_prob` per game median 27 vs distinct `market_prob` per game median 49 --
     the model moves about half as often as the line.
   Cross-check on the wider `ingame_grade` store: mlb dup 2.09 pct / held market 74.96 pct /
   held model 91.70 pct; soccer_intl dup 2.28 pct / held market 62.71 pct / held model
   63.19 pct.
4. **Verdict: BUILDABLE NOW -- and this is the arithmetic behind n_eff 420-483 of 47,104.**
5. **Bar:** a dedup + held-flag pass that reports, for every existing in-game verdict, n,
   n_informative and n_eff side by side, and re-scores e4 and the market on the informative
   subset. No new bar is cleared; the deliverable is that no future in-game CI is quoted on a
   raw tick count. Blocking condition: the re-scored e4 must reproduce to < 1e-9 on the full
   set before the informative-subset number is quoted.

## L6 -- phase recalibration

1. **Exists.** `scripts/platformkit/ingame/bucket_recalibration.py` -- **Platt**, two specs
   (`_fit_phase_platt` :92, `_fit_phase_platt_margin` :113), bucket =
   `phase|margin` where phase is inning 1-3 / 4-6 / 7+ and margin is the 5-way run-diff bucket
   from `state_bucket_benchmark.py:63-74`. **No outs, no leverage.** OOF by walk-forward date
   (`walk_forward_recal` :128-155, `BURN_IN_FRAC = 0.2`).
   `ingame_blend_recal.py` -- **isotonic** per time bucket (`_fit_iso` :72, `_N_BUCKETS = 4`
   on `frac_elapsed`), OOF by game-id parity (`split_ab` :223). `ingame_blend_recal_multisport.py`
   reuses it per sport. `ingame_recal_producer.py` / `ingame_recal_persist.py` fit-and-persist;
   `ingame_recal_apply.py` is serve-side apply only.
2. **Scored: YES once, on a DIFFERENT partition, and it is not a market-relative verdict.**
   `data/frontend/ops/mlb_bucket_recalibration.json` (2026-07-12): walk-forward over 14 dates
   / 3 burn-in, eval **36,559 ticks / 128 games**. Pooled raw Brier 0.242978 (ECE 0.079158) ->
   recal 0.230308 (ECE 0.047020); market 0.195847. `delta_vs_raw` +0.005071 CI
   [-0.005181, +0.015377] = **NO_CHANGE**; `delta_vs_market` -0.035773 CI
   [-0.051780, -0.020203] = **MODEL_BEHIND**. Per-bucket, three IMPROVED:
   `late|leading_big` 0.3745 -> **0.2759** (n 2,128 / 66 games), `late|trailing_big`
   0.2267 -> 0.1957, `late|trailing` 0.2367 -> 0.2227; every other bucket NO_CHANGE.
   Two in-sample defects inside that run, both already logged in
   `docs/research/organization-sprint/HARNESS_REDTEAM_2026-09-01.md:260-261`: the winner spec
   is chosen at :213 by the lowest Brier on the same eval set the CI at :222 then rules on
   (K=2, uncorrected), and :226 refits the persisted params on all history.
   A **second** OOF per-phase result exists on disk and is an **orphan** -- computed,
   persisted, never reported: `data/cache/probe_R12_B32_recal_winprob_endQ{1,2,3}.json`,
   producer `scripts/probe_R12_batch32_inplay_rebaseline.py` (outer expanding walk-forward
   `_wf_indices` :55 + inner 3-fold OOF `_oof_stack_with_inner_oof` :85, Platt at :148).
   Phase = end-of-quarter snapshot, NBA, 4,910 games / 3 folds: Brier 0.20786 -> 0.19942 (Q1),
   0.17338 -> 0.16808 (Q2), 0.13092 -> 0.12490 (Q3), AUC flat (0.7614/0.8337/0.9052) --
   calibration only, no added discrimination. It has **no CI, no clustered bootstrap, no
   verdict field and no market baseline**, and `grep` finds zero references to `probe_R12_B32`
   anywhere in `docs/`. Treat it as an unreviewed cache artifact, not a result: it is from the
   same end-of-quarter probe lineage as the RETRACTED endQ3 figure (see
   `.claude/rules/no-edge-claims.md`), so nothing from it may be quoted as a live number
   without a market baseline and a CI. Neither artifact is cited by the gap map, whose L6 row
   still asks "OOF per phase?" as an open question.
   The isotonic in-game path has **never produced an artifact**: `nba_recal.json` does not
   exist, so `ingame_recal_apply.load_recal_map` returns None and serve is identity; the only
   blend artifact `data/cache/ingame/ingame_blend_proof.json` is self-labelled
   `"corpus": "SYNTHETIC"`. S05's OOF per-regime isotonic
   (`docs/evidence/calibration/*_reliability_2026-09-03.json`) is pregame, keyed on
   month x confidence tercile, and **flattened all four sports without improving any**.
   S43 is the adjacent descriptive in-game report (max-loser-WP p50/p90 0.6700/0.9059 for e4
   vs 0.6200/0.8900 for the market; e4 puts > 0.8 on the eventual loser in 13 of 81 loser
   games vs the market's 12).
3. **Data: PRESENT.** The 47,104-tick scored partition carries inning (66.65 pct) and score, so
   `phase|margin` is derivable at every scored tick; `outs` is derivable on 66.53 pct.
4. **Verdict: BUILDABLE NOW.** A per-phase recal exists and shows a real effect in
   `late|leading_big`, but it has never been run OOF **on the S06/S58 scored partition against
   e4 and the line**, and its one run selected its own winner in sample.
5. **Bar:** per-phase recal of the e4 blend, fit strictly inside the outer folds, scored on the
   47,104-tick set: **>= +0.004 on the worst-calibrated phase** (`late|leading_big`, e4 to be
   re-scored per phase first) with **no phase degraded by more than 0.001**, spec chosen inside
   the folds, family-of-one BH bar declared before the first p-value.

## L7 -- freshness / lead time

1. **Exists.** `freshness_premium.py` -- the MARKET's own Brier by time-to-start on the price
   series (`HORIZONS` :72, `_devig` :158, `model_placement` field literally `"QUEUED"` :264).
   `inplay_tick_latency.py` -- OUR capture cadence (`LIVE_GAP_MAX_SEC = 900`, GREEN iff
   p90 <= 120 s); venue lag only if a row carries `src_ts`, which none does.
   `quote_freshness.py` -- the FRESH/STALE mask and `state_age_sec`.
   `freshness_model_placement.py:140 nba_placement` -- model vs market **at the same
   horizon t**. `ingame_freshness_cross_corpus.py` -- replication adjudication.
2. **Scored: the market side YES, a lead-time screen NEVER.**
   `data/frontend/ops/inplay_tick_latency.json`: mlb 371 games / 79,441 ticks, gap **p50 31.0 s
   / p90 82.0 s** (GREEN); soccer_intl 68 / 9,182, p50 29.0 / p90 52.0; tennis 812 games but
   0 gap samples (INSUFFICIENT). **The gap map's "tick latency p50 15 s" does not match this
   artifact -- the measured figure is 31 s.** `schema_has_venue_ts: false` everywhere.
   `data/frontend/ops/freshness_premium_curve.json`: MLB 925 games kept, market Brier
   T-24h 0.24726 -> last pregame tick 0.24542; mean absolute open-to-close move 0.02214.
   `data/frontend/ops/freshness_model_placement.json`: NBA n=44, model 0.21457 flat vs market
   0.20692 -> 0.19933, every CI contains 0; tennis n=357 at T-15m, model 0.21487 vs market
   0.20030, delta +0.01457 CI [+0.00076, +0.02995] -- model behind at three horizons.
   `data/frontend/ops/latency_audit.json`: 154 events, 135 matched, event-to-reprice median lag
   **34.0 s** (p25 16, p75 86), typical move 4.0 pp; `pct_events_we_led = 1.0` is labelled a
   tautology of the forward-only search, and the honest counter-check found Kalshi already
   moving >= 2 pp before our poll in **129/135 (95.6 pct)**; our GUMBO cadence median 54 s vs
   Kalshi 7 s; `feasibility_verdict: "Not established"`.
   A `model-at-t vs market-at-t+30s` screen: **NEVER** -- every model-vs-market comparison on
   disk is same-timestamp.
3. **Data: PRESENT for cadence and for the market curve; ABSENT for the anticipation screen.**
   A 30 s offset is below our own p50 inter-tick gap (31 s), so on the current corpus the
   screen is under-resolved by construction.
4. **Verdict: BLOCKED at the stated 30 s grain** (capture cadence 31 s p50 / 82 s p90, no
   `src_ts` on any tick); BUILDABLE at a coarser offset (>= 120 s, i.e. p90).
5. **Bar:** state the offset as a multiple of the measured p90 (82 s), not 30 s. A screen of
   model-at-t against the market's next tick at t + 120 s on the 47,104-tick set, reporting the
   share of ticks where a next tick exists inside the window, plus the lead-time distribution.
   Honest NULL is the expected and acceptable outcome.

## L8 -- cross-sport ticks

1. **Exists.** Per-sport capture under `data/cache/ingame_grade/<sport>` and
   `ingame_grade_joined/<sport>`; per-sport price series under `data/cache/inplay_odds/`.
2. **Scored: MLB yes (e4, above); NBA yes at ONE checkpoint per game.**
   `RESULTS_LEDGER_SYSTEM.md:193` (S58 trial B, charged at K=17): NBA halftime, as-of Elo prior
   + pure repricer vs the Polymarket in-play price on **1,593 / 1,593 games**, model Brier
   **0.171360** vs market **0.164777**, improvement -0.006583 (bar unmet), DM CI
   [-0.011503, -0.001664], deflated p 0.148822, ECE 0.054303 vs 0.017047; units 2024-25
   n 656 (-0.011575) and 2025-26 n 937 (-0.003089), replicated on 0/2. Soccer: only the
   descriptive CRPS-market run (Brier at minute 60/75, n 22 and 17, both UNDERPOWERED).
3. **Data, measured this session (`ingame_grade`, paired = model+market on the same row):**

   | sport | files | rows | games | paired rows | settled games | range |
   |---|---|---|---|---|---|---|
   | mlb | 405 | 79,566 | 401 | 79,170 | 396 | 2026-06-19..09-01 |
   | soccer_intl | 69 | 9,183 | 69 | 9,126 | 57 | 2026-06-22..08-31 |
   | tennis | 1,238 | 1,255 | 1,238 | **18** | 1,237 | 2026-07-04..09-01 |
   | wnba | 3 | 280 | 3 | 280 | **0** | 2026-07-19 |
   | nba | 2 | 2 | 2 | 1 | 1 | 2026-07-05..07-18 |

   `ingame_grade_joined` (with an `outcome` column): mlb 78,986 / 227 games; soccer_intl
   9,003 / 51 games; nothing else. Separately, **`nba_checkpoints_full.parquet` is a full
   state x line x outcome tick corpus of 465,249 rows / 1,593 games** (L4).
4. **Verdict: ALREADY MET for NBA (1,593 games, far above the >= 200 bar) -- but only one tick
   per game has ever been scored. DATA ABSENT for tennis (18 paired ticks), wnba (0 settled)
   and live-nba capture; soccer_intl is real but 51 games, below the bar.**
5. **Bar:** score all 465,249 NBA ticks, not one per game, with the same as-of prior; report
   both corpus units and require `n_corpora_eff >= 2` before any TWO-CORPORA label.

## L9 -- arm registry sweep

1. **Exists, but there is no registry.** `scripts/platformkit/ingame/arm_registry.py` (77
   lines) defines `ArmSpec`/`ArmResult`, `run_shadow` :46, `verdict` :67 and the locks
   `MEASURED_DELTA_BRIER_LOCK = -0.03425595343964605`,
   `MEASURED_EFFECTIVE_N_LOCK = 268.0`, `MINIMUM_DELTA_BRIER_IMPROVEMENT = 0.004`,
   `MARKET_GUARD = 0.15` -- **it constructs no `ArmSpec` and contains no table**. The only
   enumeration is `arm_evaluation.py:11 ARM_NAMES = ("gap_blend", "gap_offset", "gap_regime")`,
   and `arm_evaluation.evaluate` :28 hardcodes `verdict(None, None, 0, None, False)`, so it can
   only ever emit INSUFFICIENT. The name-to-module mapping lives only in callers
   (`run_gap_arms_real_corpus.py:12`, `hedge_trial_arms.py:107-119`). The dict was proposed
   (`docs/research/organization-sprint/QUANT_INGAME_RESEARCH_2026-09-01.md:947`) and never
   built. Separately, **`arm_registry.verdict` :67 carries a documented SIGN DEFECT and is
   barred from use as a gate** by four specs (`docs/evidence/tracking/specs/S06_spec.md:26`
   and three organization-sprint plans); the proposed fix `PROPOSED_hedge_2026-09-01.md` is
   unapplied because `arm_registry` is shared. Observed effect: it printed `SHIP_TO_SHADOW` on
   soccer_intl at gap -0.0961, where the real verdict is BEHIND
   (`HEDGE_TRIAL_RESULT_2026-09-01.md:96`).
2. **Scored (the table the register asked for):**

   | arm | module | corpus | last leak-free score vs the line |
   |---|---|---|---|
   | `gap_blend` / e4 | `gap_blend_arm.py:121 evaluate` | `ingame_grade_joined/mlb`, signal = `score_diff` | **0.206785778212713** on 47,104 / 158 (market 0.195387); 13 outer folds; incumbent at K=14,15,16 |
   | `gap_regime` / e2 | `gap_regime_arm.py:98 evaluate` | same, in-window ticks only | **0.254350980569169** on 6,579 / 157 vs e4 0.206078783710964 on the same slice; DM CI [-0.072123, -0.024422]; deflated p 0.0014753 at K=15; BEHIND |
   | `gap_offset` / e1 | `gap_offset_arm.py evaluate` | same | **0.281762477954033** on the 6,579 intersection, 0.280614525620140 on the 47,104 set; entered S06 as an arm at K=14; never charged alone |
   | `gap_leadoff` | `gap_leadoff_arm.py:180 run` | `mlb_atbat_states__{2022,2023}` train / `__{2024,2025}` eval -- **no tick line anywhere in the module** | **NEVER.** `data/frontend/ingame/leadoff_arm_gate_mlb.json` = `REJECT`, `missing_pre_registered_atbat_evaluation_corpora`; no Brier at all |
   | `hedge_combiner` | `hedge_combiner.py evaluate` | arm series over the same store + `ingame_grade_joined/soccer_intl` | **scored and charged at K=12 but NOT leak-free**: hedge 0.2236563334176751 vs market 0.195387 on 47,104 / 158, BEHIND; soccer_intl 0.2699139078515225 vs 0.1738535457106975 on 6,388 / 39, BEHIND. Its e4/e2 inputs were the shipped tick-date series, proven self-leaking at 52.86 pct and 43.49 pct of scored ticks (`S06_OOF_PREFLIGHT:33-52`, gap **S36 OPEN**) |
   | `gap_effective_n` | `gap_effective_n.py` | any differential frame | not an arm (ICC / deff / n_eff helper) |

   ESS label collision to resolve in the same table: two ICCs circulate on the same 47,104
   ticks -- 0.207 / deff 62.4 / n_eff 754.5 for the *shipped leaky* e4 0.207033 series
   (`E4_PROMOTION_RESULT_2026-09-01.md:41`) and 0.291 / 87.4 / 539.1 for the hedge
   differential. The leak-free e4 0.206786 has no separately published ESS; S43's 420-483 is
   for its descriptive series and S06's stacker differential is 296.61098781510543.
3. **Data: PRESENT** for every arm except `gap_leadoff`, whose declared eval corpora
   (`mlb_atbat_states__2024.parquet`, `__2025.parquet`) are **absent from disk** -- only
   `__2022` (14,734 rows) and `__2023` (13,546 rows) exist.
4. **Verdict: ALREADY DONE by this memo for e4/e2/e1; BUILDABLE NOW for `hedge_combiner`
   (a re-run on the leak-free arms); DATA ABSENT for `gap_leadoff`.**
5. **Bar:** one table on the SAME screen partition. Drop `gap_leadoff` from the register until
   its 2024/2025 at-bat corpora exist. Re-run `hedge_combiner` on the game-first-date arms;
   if it stays behind e4, retire it. No charge -- this is a screen-side housekeeping table.

## L10 -- event-reactive model

1. **Exists.** `scripts/platformkit/ingame/mlb_event_reactive.py` is the missing PRODUCER
   (`extract_events` :90 emits pitch / pa_end / run_scored / inning_change from the GUMBO
   payload with a stable `playId`; `build_rows` :126 emits `ts`/`src_ts` aliases of
   `detect_ts`/`event_ts` plus signed `lag_ms`; `summarize` :201; `run_live` :234). The
   CONSUMER is `latency_scoreboard.event_reactive_supported`, a fail-closed two-part gate:
   `lag_p90 <= 5.0 s` AND `src_ts` coverage `>= 95.0 pct`.
2. **Scored: NEVER as a model.** The only measurement is the latency audit under L7
   (median 34.0 s, 95.6 pct of matched events already moving before our poll).
3. **Data: essentially ABSENT.** `data/cache/event_reactive/mlb/` holds **6 game files, 88
   rows**, plus 87 rows in `_scoreboard_scratch`. Every existing tick writer emits our own
   capture clock only -- `schema_has_venue_ts: false` on all four sports, so `src_ts` coverage
   is 0 pct against a 95 pct gate.
4. **Verdict: BLOCKED.** Not by modelling: by capture. Our GUMBO poll cadence is 54 s median
   against a 5 s gate, and no historical tick carries a source timestamp, so no retrospective
   scoring is possible on any corpus on disk.
5. **Bar:** a capture lane, not a model lane. `src_ts` on >= 95 pct of newly captured MLB ticks
   and `lag_p90 <= 5 s` over >= 200 events, before any event-reactive model is scored. Report
   the honest ceiling (34 s / 95.6 pct) in the same memo.

## L11 -- multiplicity for in-game

1. **Exists.** `scripts/platformkit/eval_gate/family_bars.py` defines **zero** families -- it
   parses them at `load_families` :126 from the frozen spec
   `docs/evidence/harness/FWER_FAMILIES_SPEC_2026-09-03.md`, pinned by
   `git hash-object 62702554f6e57ec9f3182e8edc1e4d6a109a3b41` and stamped into every verdict as
   `families_spec_sha`. `dual_bar_verdict` :155 requires BOTH a global Bonferroni deflation on
   the caller's K and a within-family BH/BY step-up at q = 0.05, with the q-rule read off the
   spec **before** any p-value (:176-180); `raw_p` must be a member of `family_p_values` or it
   raises. K is an argument -- the module opens no ledger.
2. **Scored: n/a.** The spec is frozen at **37 families / 396 features / 3,564 hypotheses**.
   **11 of the 37 carry `horizon: live_tick, market: inplay`** -- `mlb_atbat_states`,
   `mlb_pitch_states`, `mlb_states`, `nba_pbp_foul_states`, `nba_pbp_states`,
   `nba_possession_states`, `soccer_cardstates`, `soccer_shotstates`, `soccer_shotxgstates`,
   `soccer_states`, `tennis_states`. **All eleven are feature-column grids, not arm families.**
   There is **no in-game ARM family**: `ingame_mlb_arms` (K=15) and `ingame_mlb_clamp` (K=16)
   are both explicitly NOT in the frozen partition and were charged as families of one via
   `_charge_ledger` by hand; `ingame_nba_halftime_asof` (K=17) likewise.
3. **Data: PRESENT** (the frozen spec file and the family parser).
4. **Verdict: BUILDABLE NOW, and it is a precondition, not an option** -- three in-game charges
   have already landed against families the frozen partition does not contain.
5. **Bar:** an in-game ARM family (or families) added to the frozen spec, committed alone, its
   `git hash-object` re-pinned in `family_bars.py`, **before** the next in-game charge. No
   verdict already charged may be re-scored under the new partition; the three existing rows
   stay labelled family-of-one.

## L12 -- forward

1. **Exists.** `scripts/platformkit/ingame/forward_evidence_scoreboard.py` -- a read-only
   composer over `data/domains/<sport>/ingame_tail_verdict.json` and the enrichment-gate
   verdicts; it never recomputes a statistic.
2. **Scored: no forward settled series exists yet.**
   `docs/evidence/harness/S07_forward_primacy_2026-09-03.md`: **12 of 17 scoreboard rows have
   `forward_n == 0`**; the best row is `tail_H1_longshot_underpriced` with `forward_n: 1`,
   `days_accruing: 61.2`, `distance_to_decidable: "1163_DAYS"`. The memo states plainly that no
   forward settled series exists.
3. **Data: ACCRUING AT ZERO.** The `E4-REPL` ledger line measured accrual at **0 games in the
   1.79 days** from runner boot to heartbeat = 0.00 games/day, with
   `grade_write_fail_by_reason {no_live_state: 95}` on 95 of 95 scheduled games (the S32
   diagnosis: `data/domains/mlb/games.parquet` absent on the pod). Window 2 (S55) has never had
   its game count measured; both S72 and S58-trial-A name that as the blocker for a re-charge.
4. **Verdict: BLOCKED (upstream capture), report only per the register.**
5. **Bar:** report `forward_n` per row each session. The unblock is the pod capture fix, not a
   modelling lane; the next in-game re-charge is gated on S55 reaching >= 30 MLB games.

---

# New territory (L13-L20)

## L13 -- sensor fusion (filter the market's tick SERIES)

1. **Exists: nothing.** `grep` for `kalman|KalmanFilter|state_space|particle_filter` over
   `scripts/platformkit/` returns **no files**. The incumbent `gap_blend_arm` is a
   one-parameter static logit blend (`_fit_weight` :69) with a +/-0.15 market guard -- exactly
   the single-weight form the lever contrasts with.
2. **Scored: NEVER.**
3. **Data: PRESENT.** Both series exist per game per tick in `ingame_grade_joined/mlb`
   (78,986 rows / 227 games) and `soccer_intl` (9,003 / 51). Observation-noise inputs are
   measured: inter-tick p50 31 s / p90 82 s, cross-venue reprice lag median 34 s, and the
   held-position shares from L5 (market held 74.97 pct, model held 91.71 pct) which are the
   dominant nuisance a filter would have to model.
4. **Verdict: BUILDABLE NOW.** The honest caveat: with the model series changing on only
   8.29 pct of tick transitions, a filter is mostly filtering the market against a nearly
   piecewise-constant model, and that should be stated in the prereg.
5. **Bar:** two numbers, not one -- **>= +0.004 vs e4 0.206786** on the 47,104-tick set AND
   posterior-interval coverage within 2 points of nominal, both on the SCREEN partition, with
   the filter's observation noise fit inside the folds.

## L14 -- market-consistent simulation (fit one distribution to every in-play market)

1. **Exists, pregame only.** `scripts/platformkit/benchmarks/crps_market/market_dist.py` turns
   devigged (line, P(over)) pairs into a market-implied Gaussian(mu, sigma) -- a least-squares
   probit fit when >= 2 distinct lines exist, a climatology-sigma fallback at 1 line. It reads
   `line_history`, not the in-play tick series. Nothing joins two in-play markets on the same
   game.
2. **Scored: NEVER in play.** The pregame run
   (`crps_market/last_run_mlb.json`) is total_runs: 300 games scored, model CRPS 2.9331 vs
   market 2.8808, paired delta -0.0523 CI [-0.1657, +0.0482], 80 pct coverage 0.75 vs 0.81,
   verdict UNDERPOWERED.
3. **Data: PRESENT but keyed apart.** Secondary in-play markets on disk (from
   `inplay_odds/*_price_series.parquet`, all with `result_where_known`):

   | sport | moneyline | spread | total / team_total |
   |---|---|---|---|
   | mlb | 12,817,077 rows / 3,792 ev | 130,457 / 41 | **526,057 / 99** |
   | kbo | 482,959 / 195 | 366,422 / 150 | 564,934 / 213 |
   | wnba | 217,702 / 98 | 484,729 / 130 | 264,671 / 59 |
   | soccer_intl | 963,546 / 96 | 609,424 / 96 | 688,933 / 96 (team_total) |
   | nba | 8,092,183 / 1,826 | 307,449 / 9 | none |

   **`event_key` is market-type-specific, so 0 events carry more than one market type today.**
   The re-key is mechanical: the keys differ only by series prefix
   (`KXWCGAME-26JUL01BELSEN` / `KXWCSPREAD-26JUL01BELSEN` / `KXWCTEAMTOTAL-26JUL01BELSEN`;
   `KXMLBGAME-26JUL011235CWSBAL` / `KXMLBTOTAL-26JUL011235CWSBAL`). After a prefix strip,
   **soccer_intl gives 96 games carrying all three markets** and MLB up to 99 games carrying
   moneyline + total. `kalshi_series_spec.py:62-104 SERIES_SPEC` is the authoritative
   market-type enumeration (`moneyline | total | spread | team_total`); `market_set.py` has
   none. The secondary markets also appear in the depth stores (`book_depth`: KXWNBASPREAD
   26,418 rows / 27 games, KXWNBATOTAL 12,495 / 23, KXMLBTOTAL 8,502 / 43, KXMLBTEAMTOTAL
   4,347 / 16, KXMLBSPREAD 2,157 / 41). **The scored side is moneyline-only**:
   `ingame_grade*` carries no `market_type` column at all and every
   `ingame_grade_joined/mlb` game_id is `KXMLBGAME-*`.
4. **Verdict: BUILDABLE NOW for soccer_intl (96 games x 3 markets); THIN for MLB (99 games).**
5. **Bar:** step 0 is the re-key with a measured join rate (report games matched of 96 and of
   99, never assume). Then **>= +0.004 vs the moneyline-alone series on ticks**, with the
   totals leg scored by CRPS in the same run so the claim covers the surface it says it does.

## L15 -- microstructure state (book depth, queue, trade direction)

1. **Exists.** `ingame_book_depth.py`, `_kalshi.py`, `_poly.py`, `_poller.py`,
   `_retention.py` plus `odds_provider/kalshi_tick_depth.py` and `depth_capture.py`.
2. **Scored: NEVER.** No artifact scores a microstructure feature against outcome or against
   the next-tick move.
3. **Data: PRESENT and large, measured this session.** `data/cache/book_depth/` = 568 MB,
   23 files:
   - `_archive/kalshi/`: **277,888 rows / 14 files / 2026-07-04..2026-07-17 / 313 distinct game
     tickers** (mlb 134,580, wnba 143,308). Fields: `ts, venue, ticker, best_bid, best_ask,
     spread_bp, book_thinness, n_levels, last_trade_ts, trades_last_5m, stale_quote_flag,
     sport`.
   - `_archive/kalshi_trades/`: **2,070,472 rows / 9 files / 2026-07-09..2026-07-17 / 156 game
     tickers** (mlb 1,060,539, wnba 1,009,933). Fields: `trade_ts, trade_id, price, count,
     taker_side, ts, ticker, sport` -- **`taker_side` is last-trade direction**.
   - The live (non-archive) `kalshi/` and `kalshi_trades/` dirs are empty.
   - A reduced form is already on the ticks: `spread_bp`, `book_thinness`, `stale_quote` on
     **25,585 of 79,566** `ingame_grade/mlb` rows (32.16 pct).
   - **A second, full-ladder store exists**: `data/cache/depth_history/<sport>/<date>.jsonl`
     from `odds_provider/depth_capture.py` -- **107,356 rows / 82 files / 6 sports / 2,340
     tickers / 765 event_tickers, 2026-07-05..2026-09-02** (dense body ends 2026-07-27; the
     September tail is 200 rows over 62 seconds). Fields `ts, sport, ticker, event_ticker,
     yes_bids, yes_asks, depth_totals, source, source_url, fetched_at, capture_version` --
     **`yes_bids`/`yes_asks` are the RAW per-level [price, size] ladders**, so depth imbalance
     and queue at the touch ARE derivable here. It carries no spread, no trades, no stale flag,
     and it is in **no retention policy** (`sidecar_retention.DEFAULT_POLICY` covers
     `book_depth` at 30 d / 2 GiB but not `depth_history`).
   Honest limits: in `book_depth` there are **no per-level sizes** -- `book_thinness` is a
   top-3 aggregate per side (`ingame_book_depth_kalshi.py:87,95`) and only `n_levels` survives,
   so imbalance and queue-at-touch are NOT derivable from that store; the two stores must be
   joined to get ladder + spread + trades together. `count` is null on 58,476 trade rows
   (2.8 pct, the pre-`count_fp`-fix window). **Polymarket depth is ABSENT** -- the reader
   exists, zero rows on disk.
   Window overlap with the scored MLB corpus (2026-06-20..07-12) is **2026-07-04..07-12 for
   `book_depth`, 2026-07-09..07-12 for trades, 2026-07-05..07-12 for `depth_history`** --
   roughly 9, 4 and 8 days.
4. **Verdict: BUILDABLE NOW, on a short overlap.** Every feature the lever names is derivable
   once `book_depth` and `depth_history` are joined on `(ticker, ts)`; from `book_depth` alone
   the headline depth-imbalance feature would be DATA ABSENT.
5. **Bar:** state the overlap n first (games and ticks in 2026-07-04..07-12 after the ticker
   join). Then next-tick sign accuracy **> 50 pct with a game-clustered CI excluding 0.50**,
   and separately **>= +0.004 vs e4** on the outcome Brier over the overlap slice with e4
   re-scored on the same slice.

## L16 -- overreaction residual (does the market overshoot after an event?)

1. **Exists, as the inverse measurement.** `gumbo_mlb_poller.py` + `mlb_event_reactive.py`
   (event extraction, above) and the completed audit
   `docs/research/latency_audit_2026_07_07.md` / `data/frontend/ops/latency_audit.json`, which
   already measures the market's post-event move (typical 4.0 pp) and its timing.
2. **Scored: NEVER at event grain.** The audit scores timing only, and its own
   `feasibility_verdict` is "Not established". The nearest existing measurement is
   `scripts/platformkit/analytics_showcase/out/market_overreaction.json` (producer
   `market_overreaction.py`), which is explicitly **consecutive-row grain, not
   event-triggered** (its own `ponytail:` comment at :70 and the artifact's
   `novelty.how_ours_differs` say so): `moved_to_minus_outcome` by |delta| band, MLB +0.0689 /
   +0.0533 / +0.0801 / +0.0656 / +0.0518 (n 66,697 / 7,339 / 2,860 / 1,069 / 794),
   soccer_intl -0.1945 / -0.2472 / -0.2779 / -0.3648 / -0.2760 (n 7,791 / 946 / 103 / 21 / 91).
   `docs/evidence/novel-analytics.md:112-118` records the honest reading: this is a
   directional-bias check, and raw moved-to price against outcome conflates market bias with
   the win-prob convention and the vig. It is not an overshoot measurement.
3. **Data: THIN, and the event store does not overlap any market capture.** Events joined to
   ticks in the audit: 154 events, **135 matched**, over four days (2026-07-04..07-07).
   `data/cache/event_reactive/mlb/` holds **6 games / 88 rows, all inside a single 5.7-minute
   window 2026-09-01T23:25:11..23:30:55**, of which only **2 are `run_scored`** (pitch 65,
   pa_end 17, inning_change 4); `book_depth` ends 2026-07-17 and the nearest `depth_history`
   rows are ~5.4 h later on future-dated tickers, so **zero events on disk are joinable to a
   market tick within +/-120 s**. (Its rows also predate a field rename -- they carry
   `feed_lag_ms`/`poll_lag_ms` while `mlb_event_reactive.py:147-148` now writes
   `feed_stamp_delta_ms`/`observe_lag_ms`, so `summarize()` reports None on this store.)
   The usable substrate is one level coarser: **`data/domains/mlb/gumbo_live/_archive/` =
   123 files (123 game_pks) / 44,015 rows / `captured_at` 2026-07-07..2026-07-15**, columns
   `game_pk, ts, captured_at, inning, half, outs, balls, strikes, base_state, base_label,
   on_first/second/third, batter_id, pitcher_id, pitcher_pitches, pitch_velo_last,
   score_home, score_away`. **40,272 of 40,291 rows carrying `captured_at` (100.0 pct) fall
   within +/-120 s of a `KXMLBGAME` depth tick.** The blocker is the ID join, not time: GUMBO
   keys on `game_pk`, the market keys on Kalshi ticker, and the bridge cache
   `data/domains/mlb/game_pk_bridge/` holds **one file (2026-07-03)** which does not cover the
   07-07..07-15 window. No tick carries `src_ts`, and our poll
   cadence (54 s median) is 7.7x the Kalshi quote cadence (7 s), which the audit itself says
   cannot resolve ordering. Score changes ARE recoverable from `state_summary` on the 66.65 pct
   of scored ticks carrying inning + score, which gives a larger event set than 135 without any
   new capture.
4. **Verdict: BUILDABLE NOW at tick resolution (score-change events derived from
   `state_summary`), BLOCKED at event resolution (135 matched events, no `src_ts`).**
5. **Bar:** define the event as a score change between consecutive ticks; measure the market's
   cumulative move over the following 120 s (>= p90 cadence) and regress the eventual outcome
   on that move. Report the overshoot with a game-clustered CI. An honest NULL is the expected
   result and must be recorded either way; only a CI excluding 0 justifies an arm, which then
   needs **>= +0.004 vs e4** on the screen side.

## L17 -- adaptive conformal on ticks

1. **Exists.** `scripts/platformkit/ingame/aci_online.py` -- Gibbs+Candes 2021 online alpha
   update (`aci_update` :25, `apply_aci_to_band` :40, `run_aci_stream` :64, `run_planted_null`
   :135, `gate_aci_on_stream` :159), defaults `gamma = 0.01`, `alpha_target = 0.10`,
   `_MIN_STREAM_LEN = 50`; leak-free by construction (alpha at t uses only misses <= t-1);
   default-OFF gate. It emits `aci_coverage, static_coverage, nominal_coverage, aci_gap,
   static_gap, aci_width_mean, static_width_mean, aci_pinball, static_pinball,
   alpha_trajectory`. `_main()` :217 is a synthetic demo. `aci_stream_shim.py` is the
   persistence seam (`update_stream` :97 over `ingame_grade/<sport>`, state to
   `data/cache/ingame_aci`).
2. **Scored: NEVER.** No `aci_*` key appears anywhere under `data/cache/`; every hit in
   `docs/` is a plan or a gap statement (`COMBINATION_METHODS_2026-09-01.md:202` records the
   module as "complete and correct -- and has zero callers").
3. **Data: PRESENT for a direct run, ABSENT for the shim path.** Three independent blockers on
   the shim, all measured: (a) `data/cache/ingame_aci/` does not exist -- `update_stream`
   writes only `if fresh:` and has never had a fresh row; (b) **`ingame_grade` rows carry no
   interval band** -- `_band()` :67 needs `lo/static_lo/base_lo/interval_lo` plus a `hi` twin
   and no row variant on disk has any of them, so `_resolved_rows` skips every row; (c) the
   shim is **hardcoded to nba** (`ingame_pred_tick_runner.py:145,200`) and
   `ingame_grade/nba/` holds 2 files / 1 row each against `_MIN_STREAM_LEN = 50`. The direct
   path is unblocked: the 47,104-tick scored partition is a single ordered stream per game with
   an outcome, and phase keys are derivable (inning on 66.65 pct, `phase|margin` as in L6).
4. **Verdict: BUILDABLE NOW via a direct call, BLOCKED via the shim** (a schema gap: the
   grade rows have no interval, so the shim is a structural no-op at any corpus size).
5. **Bar:** produce a band at each tick from the model series, call `run_aci_stream` directly
   (do not route through `aci_stream_shim` until `ingame_grade` carries `lo`/`hi`), and report
   a coverage series per phase at **90 +/- 2 pct** with the planted-null (`run_planted_null`,
   `null_collapses`) reported alongside. Descriptive: no ledger charge, since coverage is not a
   Brier comparison against the incumbent.

## L18 -- hierarchical pooling across sports and phases

1. **Exists: nothing.** `grep` for `hierarchical|partial_pool` over `scripts/platformkit/`
   returns only `specs/*.py` signal DATA modules, none of which pools. The nearest thing is
   `stacker.fit_meta` :59, which fits per-regime rows with a pooled fallback at
   `< MIN_REGIME` rows -- a hard fallback, not partial pooling.
2. **Scored: NEVER.**
3. **Data: BLOCKED ON L8.** Pooling needs >= 2 sports with a model+market+outcome tick series.
   Today: MLB 78,986 ticks / 227 games and soccer_intl 9,003 / 51 in `ingame_grade_joined`;
   NBA has 465,249 ticks / 1,593 games of state+market+outcome but **no model column** until
   the L4/L8 lane produces one.
4. **Verdict: BLOCKED (depends on L8 landing an NBA model series).**
5. **Bar:** after L8, **>= +0.004 on the low-n phases with no phase degraded by more than
   0.001 on MLB**, one sport-blind blend with the pooling strength fit inside the folds.

## L19 -- momentum as a preregistered public NULL

1. **Exists as features, not as a family.** `momentum` / `hot_hand` appear only in
   `scripts/platformkit/specs/*.py` (25+ signal DATA modules: `tempovariation_*`,
   `startquality_*`, `volatilityprofiles_*`, `specialsituations_*`, ...). None of the 37 frozen
   FWER families is momentum-shaped -- the closest names, `nba_carryover` (rest days + heavy
   minute load, `horizon: pregame`) and `nba_quarter_shape` (quarter margins,
   `horizon: period, market: spread`), are not hot-hand tests.
2. **Scored: NEVER as a momentum hypothesis.**
3. **Data: PRESENT.** The spec modules exist and the in-game state corpora carry the run/score
   sequence needed to construct a streak feature.
4. **Verdict: BUILDABLE NOW.**
5. **Bar:** a preregistered family with its BH bar declared before the first p-value, and the
   verdict recorded **either way**. A null is the deliverable; it must be published as a null
   and never re-run for a different answer.

## L20 -- rest-of-game distribution scored on every in-play market by CRPS

1. **Exists.** `src/sim/rest_of_game_sim.py:344 simulate` returns the full
   `home_final_samples` / `away_final_samples` arrays and `margin_mean` / `total_mean` -- the
   distribution primitive. `benchmarks/crps_market/ingame_mlb.py` + `market_dist.py` +
   `shape_control.py` are the in-game CRPS harness. `src/**` is a human-gated path.
2. **Scored: YES, descriptively, and every checkpoint is UNDERPOWERED.**
   `crps_market/last_run_ingame_mlb.json`: 178 game files, 4 join failures; home_margin at
   end_inning_3 n=20 model CRPS 2.3943 vs market 2.8443 (paired delta +0.4499, CI
   [-0.0206, +1.0687]); end_inning_5 n=26 1.6806 vs 2.5360 (delta +0.8555, CI
   [+0.3259, +1.4888]); end_inning_6 n=22 1.4476 vs 2.4059 (delta +0.9583, CI
   [+0.2409, +1.8046]) -- `shape_control_verdict` UNDERPOWERED on all.
   `last_run_ingame_soccer.json` falls back to Brier and records why: "CRPS not constructible"
   (a single scalar per row, no distribution engine for soccer); minute_60 n=22 model 0.2961 vs
   market 0.2030; minute_75 n=17 0.3719 vs 0.2645.
3. **Data: totals ticks PRESENT but thin** -- MLB `total` 526,057 rows / 99 events,
   kbo 564,934 / 213, wnba 264,671 / 59, soccer_intl team_total 688,933 / 96; NBA has **no
   totals series at all**. Margin/spread: MLB 130,457 / 41, NBA 307,449 / **9**.
4. **Verdict: BUILDABLE NOW at low n (99 MLB total-games), and the existing checkpoint result
   is a genuine positive-direction signal that has never been powered.**
5. **Bar:** move from ~22 games per checkpoint to the full 99 MLB total-market games, scoring
   per tick rather than per checkpoint; CRPS vs the market-implied distribution with a
   game-clustered CI, plus the `shape_control` null. The bar is a CI excluding 0, not +0.004
   (different metric -- say so explicitly rather than reusing the Brier bar).

---

# Lanes to dispatch now (ranked; buildable, data present, highest expected calibration gain first)

## 1. L4+L8 -- score the whole NBA checkpoint corpus, not one tick per game

- **Premise (verified):** `nba_checkpoints_full.parquet` is 465,249 rows / 1,593 games /
  2024-10-22..2026-06-13 with state, `market_prob` and `outcome_home_win` (0 nulls); S58 trial
  B scored **1 tick per game** because `halftime_checkpoints` :42 filters `elapsed <= 24.0`
  and takes `.tail(1)`.
- **Change:** drop the anchor. `nba_checkpoint_benchmark.price_checkpoint(p0, score, period,
  clock)` is a pure state function and the as-of Elo prior (`ratings.replay` strictly before
  `game_date`) is already built, so the same code prices every tick.
- **Bar:** paired Brier vs `market_prob` over all 465,249 ticks, game-clustered DM CI, ESS
  reported, both corpus units (2024-25 n 656 / 2025-26 n 937) through `replication_gate`.
  Screen side first; charge only if it clears. Incumbent to beat on that corpus: model
  0.171360 vs market 0.164777 at halftime.
- **Files:** `scripts/platformkit/eval_gate/s58_nba_halftime_asof_trial.py` (read),
  `scripts/platformkit/ingame/nba_checkpoint_benchmark.py`, new module under
  `scripts/platformkit/eval_gate/`.
- **Why first:** it is the only lever where a 10x corpus already sits on disk and the model
  side costs one filter removal.

## 2. L5 -- tick quality: dedup, held-position flag, n_eff on every in-game verdict

- **Premise (verified):** 69.86 pct of scored MLB ticks are fully redundant (model and market
  both unchanged); duplicate `(game_id, ts)` 2.10 pct; informative ticks 23,964 of 78,986.
- **Change:** a dedup + held-flag pass in the corpus loader path, and a required
  `n / n_informative / n_eff` triple on every in-game readout.
- **Bar:** e4 reproduces to < 1e-9 on the full set before any informative-subset figure is
  quoted; then re-score e4 and the market on the informative subset and report both.
- **Files:** `scripts/platformkit/ingame/quote_freshness.py` (reuse `freshness_mask`),
  `scripts/platformkit/ingame/gap_effective_n.py`, `run_gap_arms_real_corpus.py` (read).
- **Why second:** every in-game CI on the books is quoted against a tick count that is 70 pct
  redundant; this re-prices all of them and gates lanes 1, 3, 4 and 6.

## 3. L1 -- parse the base-out state already captured on two thirds of the scored ticks

- **Premise (verified):** `outs`/`base`/`bos`/`re`/`count` on 52,546 of 78,986 scored ticks
  (66.53 pct), `pitch_count`/`tto` on 43,989 (55.69 pct); `stacker.inning_bucket` parses inning
  and nothing else; base-out has never been scored against a line.
- **Change:** a `state_summary` parser plus one e4 variant whose signal is the base-out /
  run-expectancy state, fit inside the folds.
- **Bar:** **>= +0.004 vs e4 re-scored on the SAME 52,546-tick covered slice** (not vs
  0.206786), game-clustered DM CI excluding 0.
- **Files:** `scripts/platformkit/eval_gate/stacker.py` (read),
  `scripts/platformkit/ingame/ingame_baseout_mlb.py` (read), `gap_blend_arm.py` (read),
  new screen module under `scripts/platformkit/eval_gate/`.

## 4. L6 -- per-phase recalibration on the S06 scored partition

- **Premise (verified):** the one existing run (36,559 ticks / 128 games) shows
  `late|leading_big` 0.3745 -> 0.2759 IMPROVED, but it is a different partition, its winner was
  chosen in sample at `bucket_recalibration.py:213`, and its persisted params were refit on all
  history at :226. A second, NBA, orphan result exists
  (`data/cache/probe_R12_B32_recal_winprob_endQ{1,2,3}.json`, uncited anywhere, no CI, no
  market baseline, retracted-endQ3 lineage) -- read it as a hint, never quote it.
- **Change:** re-run per-phase recal of the e4 blend, spec chosen strictly inside the outer
  folds, on the 47,104-tick partition.
- **Bar:** **>= +0.004 on `late|leading_big`** with **no phase degraded by more than 0.001**;
  family-of-one BH bar declared before the first p-value.
- **Files:** `scripts/platformkit/ingame/bucket_recalibration.py`,
  `scripts/platformkit/eval_gate/stacker.py`, `s58_clamp_family_trial.py` (fold pattern).

## 5. L17 -- ACI coverage series on ticks (direct call, not the shim)

- **Premise (verified):** `aci_online.py` is complete and leak-free by construction and has
  zero callers that ever produced a row; `data/cache/ingame_aci/` does not exist. The shim path
  is a structural no-op -- `ingame_grade` rows carry no `lo`/`hi` band, and the shim is
  nba-hardcoded onto a 1-row corpus against a 50-row minimum.
- **Change:** derive a band per tick from the model series and call `run_aci_stream` directly
  per phase on the scored partition. Do not touch the shim.
- **Bar:** coverage **90 +/- 2 pct per phase** on the SCREEN partition, with `run_planted_null`
  (`null_collapses`) reported alongside. Descriptive; no charge.
- **Files:** `scripts/platformkit/ingame/aci_online.py`, `stacker.py` (phase key),
  `ingame_grade_joined/mlb`.
- **Why here:** cheapest lane on the list and it measures a quantity (coverage) that no Brier
  on the books can show. Note the shim blocker in the memo so nobody re-discovers it.

## 6. L15 -- microstructure features on the depth/trade overlap

- **Premise (verified):** two depth stores, complementary. `book_depth/_archive/kalshi`
  277,888 rows / 313 game tickers (2026-07-04..07-17) has spread, thinness, stale flag but
  only a top-3 aggregate; `book_depth/_archive/kalshi_trades` 2,070,472 rows with `taker_side`
  / 156 tickers (2026-07-09..07-17); `depth_history` 107,356 rows / 765 event tickers /
  6 sports (2026-07-05..09-02) has the **raw per-level ladders** and no spread/trades.
  Polymarket depth is ABSENT.
- **Change:** join the two depth stores plus trades to the ticks on `(ticker, ts)` and screen
  spread, thinness, staleness, trade direction and true depth imbalance.
- **Bar:** report the overlap n first (games and ticks after the join; the binding window is
  2026-07-09..07-12 where all three stores and the scored corpus coincide). Then next-tick sign
  accuracy **> 50 pct with a game-clustered CI excluding 0.50**, and **>= +0.004 vs e4
  re-scored on the same overlap slice** for the outcome Brier.
- **Files:** `data/cache/book_depth/_archive/{kalshi,kalshi_trades}/`,
  `data/cache/depth_history/`, `scripts/platformkit/ingame/ingame_book_depth_kalshi.py`,
  `scripts/platformkit/odds_provider/depth_capture.py`, `ingame_grade_joined/mlb`.

## 7. L11 -- freeze an in-game ARM family before the next charge

- **Premise (verified):** 11 of 37 frozen families are `(live_tick, inplay)` but all are
  feature grids; `ingame_mlb_arms` (K=15), `ingame_mlb_clamp` (K=16) and
  `ingame_nba_halftime_asof` (K=17) were all charged as families of one outside the partition.
- **Change:** add the in-game arm family (or families) to the frozen spec, commit it alone,
  re-pin its `git hash-object` in `family_bars.py`.
- **Bar:** families frozen and the SHA re-pinned before the next in-game charge; no already
  charged verdict is re-scored under the new partition.
- **Files:** `docs/evidence/harness/FWER_FAMILIES_SPEC_2026-09-03.md`,
  `scripts/platformkit/eval_gate/family_bars.py` (`SPEC_PATH` :41, hash pin :88-95).
- **Why here:** housekeeping, but it is a precondition for lanes 1, 3, 4 and 6 charging cleanly.

## 8. L14 -- re-key the price series so one game carries all its in-play markets

- **Premise (verified):** `event_key` is market-type-specific, so 0 events carry two market
  types; the keys differ only by series prefix, and a strip yields **soccer_intl 96 games x
  {moneyline, spread, team_total}** and up to **99 MLB games x {moneyline, total}**.
- **Change:** a re-key with a measured join rate, then one distribution fit jointly to the
  markets on the same game.
- **Bar:** report games matched of 96 and of 99 before any modelling; then **>= +0.004 vs the
  moneyline-alone series on ticks**, with the totals leg scored by CRPS in the same run.
- **Files:** `data/cache/inplay_odds/{soccer_intl,mlb}_price_series.parquet`,
  `scripts/platformkit/venue_history/build_price_series.py`,
  `scripts/platformkit/benchmarks/crps_market/market_dist.py`.

## 9. L16 -- overreaction residual at tick resolution

- **Premise (verified):** the event-grain path is blocked -- `event_reactive/mlb` is 88 rows /
  6 games in one 5.7-minute window with 2 `run_scored` events and **zero temporally
  overlapping market capture**. But score changes are recoverable from `state_summary` on
  66.65 pct of scored ticks, a far larger event set than the audit's 135. A richer optional
  substrate exists (`gumbo_live/_archive`, 123 games / 44,015 rows / 2026-07-07..07-15, 100 pct
  within +/-120 s of a depth tick) whose only blocker is the `game_pk` -> Kalshi-ticker bridge
  cache holding a single 2026-07-03 file.
- **Change:** define the event as a between-tick score change; measure the market's cumulative
  move over the next 120 s and regress the eventual outcome on that move.
- **Bar:** overshoot reported with a game-clustered CI, **recorded either way**; an arm only if
  the CI excludes 0, and then **>= +0.004 vs e4** on the screen side. Distinguish it explicitly
  from `market_overreaction.json`, which is consecutive-row grain, not event-triggered.
- **Files:** `ingame_grade_joined/mlb`, `scripts/platformkit/ingame/mlb_event_reactive.py`
  (read), `data/frontend/ops/latency_audit.json` (the ceiling to cite),
  `scripts/platformkit/analytics_showcase/market_overreaction.py` (the thing it is not).

## 10. L20 -- power the in-game CRPS run

- **Premise (verified):** the existing in-game margin-CRPS checkpoints favour the model
  (end_inning_5 +0.8555 CI [+0.3259, +1.4888]) but on n = 20-26 games, every verdict
  UNDERPOWERED; MLB has 99 total-market games on disk against ~22 scored.
- **Change:** score per tick across all 99 MLB total-market games rather than per checkpoint on
  22.
- **Bar:** CRPS vs the market-implied distribution with a game-clustered CI excluding 0, plus
  the `shape_control` null. State explicitly that the +0.004 Brier bar does not apply -- this is
  a different metric.
- **Files:** `scripts/platformkit/benchmarks/crps_market/{ingame_mlb.py,market_dist.py,
  shape_control.py}`, `data/cache/inplay_odds/mlb_price_series.parquet`.

**Not dispatchable now:** L2 (screened, SCREEN_NULL -- the remaining gap is capture),
L7 at 30 s (below our 31 s p50 cadence), L10 (no `src_ts` on any tick, 54 s poll vs a 5 s
gate), L12 (upstream capture blocked, 0 games/day accrual), L18 (waits on lane 1),
L3's possession-sim half (`src/**` human-gated, and its NBA state corpus carries no line).
