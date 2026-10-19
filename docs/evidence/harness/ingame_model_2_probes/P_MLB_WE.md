PROBE TASK P4: MLB win-expectancy feature and market-anchored state projection (walk-forward, two corpora)

Read PROBE_RAILS.md (same dir) first; it is binding. Then the schema card.

Context: the prospective scoreboard (scripts/platformkit/execution/ingame_scoreboard.py, scripts/platformkit/ingame/baseline_four_arm.py predict_rows, feature lists in scripts/platformkit/ingame/baseline_four_arm_features.py) fits per night: arm B = logistic on ['mid'], arm C = logistic on ['mid', *FEATURES['mlb']] where FEATURES['mlb'] = score_diff, inning, half, outs, base_1..base_7 (raw state, linear). Prior research: arm C MATCHES the mid (S347, Q17). A linear logistic on raw inning/outs dummies cannot express how a score lead's value grows as the game shortens. Hypothesis for Model 2.0: a single well-shaped feature, logit(WE) from a fixed a-priori win-expectancy formula, plus a market-anchored projection, carries the state information more efficiently. Read baseline_four_arm.py and baseline_four_arm_features.py first (how mid enters: raw mid or logit? scaling?) and mirror its fitting (same solver/regularization) so arms are comparable.

Corpus J (June-July): data/cache/ingame_grade_joined/mlb_clean/*.jsonl (227 games, fields ts, market_prob, state_summary "home_score=.. away_score=.. inning=.. half=.. outs=.. base=.. re=.. count=.. tto=..", outcome, side home). Subsample to at most one tick per 60 s per game.
Corpus K (Sept): Kalshi home-ticker (KXMLBGAME) book receipts while live from data/cache/ingame_capture_view_v2/kalshi/mlb (snapshot + snapshot_bulk; mid = (yes_bid+yes_ask)/2; drop crossed/empty) subsampled to one per 30 s per game, as-of joined to the latest live state row with capture_ts <= tick (data/cache/ingame_capture_view_v2/state/mlb); outcome from final rows; exclude and count unsettled games (09-29).

Features:
- WE(state): a FIXED normal-approximation win expectancy for the home team (constants chosen a priori and written in the script: runs per half-inning mean 0.5, variance 1.0; the batting team's current-half expected additional runs from the standard RE24 base-out table; remaining half-innings for each side from inning/half/outs; tie at the end -> 0.5 via a continuity correction; walk-off logic can be ignored but say so). Clip to [0.001, 0.999].
- PROJ (market-anchored state projection): invert the mid to an implied home strength offset mu (runs per remaining 9 innings) at the last tick where the MID CHANGED, using the same normal approximation with that tick's state; then evaluate the formula at the CURRENT state with the same mu. PROJ == mid exactly when the state has not changed since the book last moved. This is the "state delta since last book move" candidate.
- STALE_DELTA = logit(PROJ) - logit(mid).

Arms (walk-forward by date: for each scored date, train on all games with an earlier date, at least 5 prior dates for J; logistic regression mirroring baseline_four_arm):
  A: raw mid (no fit)
  B: [logit mid] (or whatever baseline_four_arm uses for mid)
  C: [mid, score_diff, inning, half, outs, base_1..base_7] (the landed arm C list)
  W: [logit mid, logit WE]
  S: [logit mid, STALE_DELTA]
  WS: [logit mid, logit WE, STALE_DELTA]
  WE_ONLY: [logit WE] (sanity: how far the fixed formula alone is from the mid)
  PROJ_RAW: PROJ with no fit.
Corpus K has only 6 dates, so for K ALSO run the cross-corpus form: fit each arm on ALL of J, score on K (out of time, different games). Report both.

Report per corpus (and cross-corpus): n_games, n_ticks, Brier and log loss per arm, paired deltas vs A and vs B with game-clustered CIs, the fitted coefficients (mean over folds) on logit WE and STALE_DELTA, and the fraction of ticks where STALE_DELTA != 0 and the Brier delta restricted to those ticks. Label any cell under 30 games INSUFFICIENT.

Write scripts/outputs to the probe dir (probe_p4_we_feature.py etc.). Final report per PROBE_RAILS.md.
