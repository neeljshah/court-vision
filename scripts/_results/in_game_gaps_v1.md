# In-Game MAE Gaps — Cycle 89f Research (loop 5)

## Context
- Pre-game MAE saturated: PTS 4.62, REB 1.90, AST 1.36, FG3M 0.89, STL 0.72, BLK 0.44, TOV 0.89
- 9 post-prediction adjustments rejected (cycles 78-87); 2 retrains rejected (84a/84b)
- Frontier: live in-game updates, intraday signals, structural blowout / foul-trouble / rest decay
- Saturated angles (do NOT re-propose; see memory_history):
  - Pull-toward-L5 / L10 (multiple weights/strengths)
  - Min-played ratio scaling (mild + strong)
  - Back-to-back blanket multiplier (validate_b2b)
  - Single-feature additive features and quantile shift (q45/q55, robust-median)
  - HGB-q50, bag5, CatBoost 4th learner, Tweedie TOV

## TIER 1 — empirically validatable on existing 19964-row holdout

### T1-A. Garbage-time exposure regressor (per-game starter minutes haircut)
- **Hypothesis:** Games where the actual final score margin exceeded a Cleaning-the-Glass-style garbage-time threshold cause starter MIN to be systematically lower than our pre-game projection. Subtract an expected-garbage-time deduction from MIN-driven volume stats (PTS/REB/AST) when the pre-game implied margin (from spread or our win-prob model) is >=8 pts.
- **Why it should work:** CtG garbage time triggers at ≥25-pt margin (12-9 min Q4), ≥20-pt (9-6 min), ≥10-pt (6-0 min) [4]. A 13+ pt spread = "high blowout risk" with 3-5 min star reduction, 2-3 min role-player reduction [1]. Our model has no margin-aware MIN adjustment; this is structural slope, not noise.
- **Honest impact estimate:** **3-8 bp MAE on PTS/REB/AST** (1 sigma). Tier-1 because effect only fires on the ~10-15% of games with double-digit spreads; per-game effect is large (~10-15% MIN cut for starters in true blowouts) but base rate is moderate.
- **Probe path:** `scripts/probe_garbage_time_haircut.py` extending validate_adjustment.py. Use pre-game spread from `season_games.parquet` (already loaded) and apply tiered MIN_played multiplier (1.0 / 0.97 / 0.93 / 0.88) for spread bins (<8 / 8-12 / 13-16 / 17+). Walk-forward 4-fold gate.
- **Source(s):** [1] landyourbets.com — "13+ points: High blowout risk … Star starters: 3-5 minute reduction"; [4] nbainrstats.netlify.app — "Minutes 6-0: ≥10 point margin"

### T1-B. Foul-rate-conditional MIN shrinkage
- **Hypothesis:** Players whose season fouls-per-36 is in the top quintile have MIN realizations with a fatter LEFT tail than our point estimate captures. Apply a foul-rate-conditional q40 pull on MIN-driven stats for these players (multiplicative shrinkage of 0.96-0.98 on MIN-coupled stats: PTS/REB/AST/TOV).
- **Why it should work:** Players averaging 4+ fouls per game have 1-2 min projection reduction [1]; high-foul-rate centers/bigs have games where they play 18 min [2]. Effect is asymmetric (foul-out, not foul-in), so a symmetric quantile pull is wrong; needs left-tail-only shrink. Pre-game model doesn't see foul-rate as a feature.
- **Honest impact estimate:** **2-4 bp MAE on PTS/REB/BLK** (1 sigma). Smaller than T1-A because the foul-foul-out tail is sharp but rare (~12% of starter-games for top-quintile foul-rate players).
- **Probe path:** `scripts/probe_foul_rate_shrink.py` — compute season PF/36 from existing per-game data (already in `season_games.parquet`), bin into quintiles, apply MIN-coupled shrinkage only on top quintile + only when player is C/PF position.
- **Source(s):** [1] landyourbets.com — "Players averaging 4+ fouls per game: Reduce projected minutes by 1-2 minutes"; [2] fantasyteamadvice.com — "high foul-rate players having games where they play 18 minutes"

### T1-C. Back-to-back veteran-age interaction (refinement of saturated blanket b2b)
- **Hypothesis:** validate_b2b previously tested a flat b2b multiplier across ALL players and got wash. The real effect is age-conditional: **veterans aged 33+ sit 80% of second nights** [1]; under-30s show only the shooting-pct decline. Apply a 0.92x MIN-coupled shrink only on (age >= 33) AND (b2b == True) AND (player_role == "starter").
- **Why it should work:** The saturated probe was too broad. Age-specific b2b effect is concentrated, large (80% sit rate translates to ~50% reduction in realized MIN for that bin), and not captured by L5 form (form catches recent results, not the discrete sit decision).
- **Honest impact estimate:** **1-3 bp MAE on PTS/REB/AST** (1 sigma). Effect is large per affected game but only ~3-4% of games have a 33+ starter on b2b.
- **Probe path:** `scripts/probe_b2b_veteran.py` — add age (from `player_advanced_stats.parquet` or compute from birth_year × season) and re-validate on the (age>=33 ∩ b2b) cell only.
- **Source(s):** [1] landyourbets.com — "Veterans 33+ years: 80% chance sits on second night of back-to-back"

### T1-D. Pace-of-game live adjustment proxy (early-quarter pace as full-game multiplier)
- **Hypothesis:** Once Q1 is complete, observed possessions in Q1 are a stronger predictor of full-game pace than the pre-game pace prior. Each player's volume stats scale ~linearly with pace, so a Q1 pace residual translates directly to a volume rescaling.
- **Why it should work:** Pace is "single most important factor for predicting totals" [10]; two-team pace averaging is the standard prior [10] but it ignores live game-state. This is the live-update analog of cycle 19's "data recency > data volume" lesson.
- **Honest impact estimate:** Pre-game holdout: **unknown — needs probe** (no Q1 pace column in current holdout). If quarter-split data added: estimated 2-6 bp MAE on PTS/REB/TOV (volume stats most pace-sensitive).
- **Probe path:** `scripts/probe_pace_q1_proxy.py` — requires extending data pipeline to ingest period-level boxscore from `nba_api.live.endpoints.boxscore` (15-20s latency [5][6]). Two-step: (1) backfill Q1 pace for historical games from PBP; (2) regress full-game pace on (Q1 pace, pre-game pace) and apply residual.
- **Source(s):** [10] rotogrinders pace projection; [5] sportsdata.io — "approximately 15-20 seconds behind TV broadcast"; [6] sportradar — "2-second TTL once the game status changes to inprogress"

### T1-E. Offensive-rebound-rate as REB-specific live feature
- **Hypothesis:** Team OREB% and opponent DREB% from the previous 5 games is currently not in the REB model. Adding team-OREB%-allowed × opponent-DREB% interaction as a REB-only feature should reduce REB MAE.
- **Why it should work:** Outlier/Action Network track "Rebound Chances" because rebound rate ≠ rebound volume; the ratio captures opportunity. Our model has pace and player REB% but not team-context REB context. REB MAE is currently 1.90 and the LGB-q50 head responds well to interaction features.
- **Honest impact estimate:** **1-3 bp MAE on REB** (1 sigma). Small because REB is dominated by player skill and pace, and team-OREB-context is partially correlated with pace.
- **Probe path:** `scripts/probe_reb_oreb_context.py` — compute team OREB% / opp DREB% rolling-5 from existing `team_advanced_stats.parquet`, add as feature only to REB head, retrain LGB-q50 single-split + WF-4-fold gate.
- **Source(s):** [help.outlier.bet] — "Rebound Chances … the rate players grab rebounds from those chances"

## TIER 2 — needs forward data accumulation (live feed required)

### T2-A. Live Q1-Q2 MIN-played extrapolation
- **Hypothesis:** Once Q1+Q2 elapse, observed MIN played by a player has near-deterministic mapping to full-game MIN unless foul trouble or blowout intervenes. A live-update model that ingests `nba_api.live.endpoints.boxscore` every 30s and re-projects PTS/REB/AST against the live line should beat the pre-game model on H2/H3/Q4 props.
- **Why it should work:** "Star player minutes in the first half are generally more predictable than second half minutes" [3]. Live boxscore latency is 2-20s [5][6], well inside the DraftKings 5-min line-update cadence [8].
- **Honest impact estimate:** **15-40 bp MAE on H2 / Q4 / live full-game props** (1 sigma, high uncertainty). Cannot estimate vs pre-game holdout because the holdout has no live data. Requires forward accumulation of live boxscore + live odds.
- **Probe path:** Build `scripts/live_boxscore_capture.py` to record `nba_api.live.endpoints.boxscore` every 30s for all live games; accumulate 50-100 games of paired (live state, final stat, live line) data. Probe is a forward-collection workstream, not a one-shot validation.
- **Source(s):** [3] halfbettips first-half betting; [5] sportsdata.io; [8] dknetwork — "player props are updated every five minutes"

### T2-B. Foul-state-conditional rest-of-game MIN model
- **Hypothesis:** Player current foul count at end of each period is the single best predictor of MIN-remaining. Build a foul-count → remaining-MIN regressor conditional on (period, foul_count, score_margin).
- **Why it should work:** Coach yank rules are near-deterministic ("2 fouls in Q1 = sit until Q2", "3 fouls in Q2 = sit until Q3" are conventional). Position-conditional [9 query]; centers/PFs higher leverage.
- **Honest impact estimate:** **10-25 bp MAE on live rest-of-game PTS/REB/BLK** (1 sigma). Same caveat as T2-A — forward data only.
- **Probe path:** Extend live capture to record per-period foul state; offline backtest using historical PBP foul logs joined to per-period MIN played.
- **Source(s):** [2] fantasyteamadvice.com — coaches "track foul trouble history to determine if starters frequently get into early trouble"

### T2-C. Reverse-line-movement signal as pre-game prediction adjuster
- **Hypothesis:** When NBA prop lines move against the public-bet majority pre-game (RLM), our model should partially follow the line move (Bayesian update toward sharper consensus). Apply ±2-5% scaling to predictions on the RLM-flagged side.
- **Why it should work:** RLM sharps had +15.5% ROI on the side-with-more-dollars in spread markets [7 search-result, sportscapping]. Translation to props is unknown but the mechanism (informed money) is the same.
- **Honest impact estimate:** **unknown — needs probe**. Requires sustained scraping of bet% + line snapshots from Action Network / VSiN / unabated. Tier-2 because we don't have the historical line-movement archive.
- **Probe path:** Begin daily snapshot of prop open vs closing lines (`scripts/snap_prop_lines.py`); after 60+ games of data, classify each line as RLM/no-RLM, regress final stat residual on RLM-flag.
- **Source(s):** [shurzy / oddsjam RLM search results] — "70% of bets … line shifts toward the underdog … +15.5% return on investment"

## TIER 3 — research-grade / multi-day builds

### T3-A. Multitask MLP with live-state input head
- **Hypothesis:** Extend cycle-23 multitask MLP (AST/STL) to accept (pre-game features, live half-state vector) so a single model serves both pre-game and live use. Joint training shares regularization across 7 stats.
- **Why it should work:** Multitask AST/STL already shipped and is the only architecture-change win of the loop. Adding live-state half should not regress pre-game (zero-vector for live half) and provides infrastructure for all of Tier 2.
- **Honest impact estimate:** **0 bp pre-game** (intentional). **20-40 bp live, IF live data accumulates**.
- **Probe path:** Refactor `models/multitask_mlp.py` to two-input architecture; gate on zero-input-equals-cycle-23-output unit test.
- **Source(s):** internal — cycle 23 ship note

### T3-B. Sharp-vs-public divergence as a fade signal
- **Hypothesis:** When our model agrees with sharp money (low public%, line moved sharp direction) but disagrees with public, our edge probability is higher than the EV calc suggests; bet larger (Kelly multiplier 1.2x). Mirror logic when we disagree with sharp.
- **Why it should work:** Kelly assumes independent probability estimate; if sharp money confirms our number, the joint signal is stronger than either alone (Bayesian fusion).
- **Honest impact estimate:** Unknown — this is **bet-sizing, not MAE**. ROI improvement only; out-of-scope for MAE-driven cycle.
- **Probe path:** Defer to ROI workstream after T2-C accumulates RLM data.
- **Source(s):** [sportscapping search result] — "side with more dollars posted a record of 53-34-5, … +15.5% return"

## TIER 4 — ops polish that compounds

### T4-A. Quantile recalibration on a rolling 60-game window
- **Hypothesis:** Cycle 40's quantile calibration scale-factor (per-stat) is currently global. A rolling 60-game recalibration would drift with the league (e.g., 3PT-rate shifts) and keep coverage at 80% empirically through the season.
- **Honest impact estimate:** **0 bp MAE** (q50 unchanged); 1-3pp on q10/q90 coverage drift over a 200-game horizon. Improves Kelly-stake honesty, not point predictions.
- **Probe path:** `scripts/quantile_calibration_rolling.py` — extend cycle 40 to compute scale on prior-60 games only, refresh every 5 games.

### T4-B. Live polling latency monitor
- **Hypothesis:** Documenting actual `nba_api.live.endpoints.boxscore` latency (vs SportsRadar 2s, vs SportsDataIO 15-20s) lets us pick the right provider when live workstream goes live.
- **Honest impact estimate:** No direct MAE. Sets up Tier-2 infrastructure correctly.
- **Probe path:** `scripts/measure_live_api_latency.py` — for 5 live games, log time-from-event to time-in-API for known triggers (3PT made, sub-out).

## REFERENCES

[1] https://landyourbets.com/how-to-make-nba-minutes-projections — "Veterans 33+ years: 80% chance sits on second night of back-to-back … 13+ points: High blowout risk … Star starters: 3-5 minute reduction … Players averaging 4+ fouls per game: Reduce projected minutes by 1-2 minutes"

[2] https://fantasyteamadvice.com/nba/rotations — "Coaches track foul trouble history to determine if starters frequently get into early trouble … high foul-rate players having games where they play 18 minutes"

[3] https://halfbettips.com/articles/nba-first-half-betting/ — "Star player minutes in the first half are generally more predictable than second half minutes … second quarter is typically the most volatile quarter in NBA basketball" (per search excerpt)

[4] https://nbainrstats.netlify.app/post/identifying-garbage-time-on-nba-play-by-play/ — "Minutes 12-9: ≥25 point margin; Minutes 9-6: ≥20 point margin; Minutes 6-0: ≥10 point margin … two or fewer combined starters on floor"

[5] https://sportsdata.io/developers/workflow-guide/nba — "approximately 15-20 seconds behind TV broadcast"

[6] https://developer.sportradar.com/basketball/docs/nba-ig-update-frequencies — "two-second TTL once the game status changes to inprogress … 3-second cache during a live game"

[7] https://www.sportscapping.com/articles/sharp-vs-square-betting-action (via search) — "sharps vs. squares matchups with at least 20% discrepancy between bet dollars and bet tickets, the side with more dollars posted a record of 53-34-5, which was good for a +15.5% return on investment"

[8] https://dknetwork.draftkings.com/draftkings-sportsbook-player-props/ — "DraftKings' player props are updated every five minutes"

[9] https://www.lsports.eu/blog/the-30-point-problem-how-basketball-blowouts-expose-trading-vulnerabilities/ — "LeBron James … projected across major books for 35+ minutes and 25+ points, was pulled early, finishing with 18 points in 29 minutes"

[10] https://rotogrinders.com/lessons/importance-of-pace-and-projecting-possessions-in-nba-dfs-1144812 — "take both teams' pace differences from league average and add them both to the league average pace"

[11] https://heatcheckhq.io/blog/nba-back-to-back-rest-analysis (search excerpt) — "back-to-backs result in a 4-5% loss in shooting percentage"

[12] https://help.outlier.bet/en/articles/9005352-potential-assists-rebound-chances-nba-advanced-data — "Rebound Chances … rate players grab rebounds from those chances"

## RECOMMENDED CYCLE 90+ ORDERING

1. **Cycle 90 — T1-A garbage-time haircut.** Highest-leverage Tier-1: structural slope, no new data ingestion needed (spread is in `season_games.parquet`), affects 3 stats (PTS/REB/AST), and addresses the saturated post-prediction-adjustment family from the RIGHT angle (spread-conditioned, not blanket).
2. **Cycle 91 — T1-C b2b veteran-age refinement.** Cheap, narrow re-test of an already-saturated probe with the correct conditioning. If positive, validates the "saturated probes need conditioning, not bigger weights" pattern for cycles 92+.
3. **Cycle 92 — T1-B foul-rate-conditional shrink.** Position × foul-rate interaction. Needs season PF/36 aggregation but no live data.
4. **Cycle 93 — T1-E REB OREB-context feature.** Single-stat targeted; lowest variance per cycle but cheap retrain.
5. **Cycle 94 — T4-A rolling quantile calibration + T4-B latency monitor.** Ops setup before any Tier-2 live workstream begins.
6. **Cycle 95+ — Tier-2 live capture starts (T2-A live MIN extrapolation).** Forward data accumulation; first 30-60 games are infrastructure-only with no MAE claim.
