PROBE TASK P1-P3: MLB book response, price source, and mid calibration (Kalshi + Polymarket, capture_view_v2; second corpus mlb_clean)

Read PROBE_RAILS.md (same dir) first; it is binding. Then the schema card.

Context: prior research (docs/evidence/harness S115, S277, S347, Gate A0) found residual models on the market mid never beat the mid walk-forward, and recalibrating the NBA mid made it worse. What has NOT been measured is on the fresh Sept 2026 Kalshi MLB capture with full focus books: (a) whether the book is still stale at the moment OUR state feed shows an event, (b) whether a better price summary than the raw mid exists, (c) whether the Kalshi MLB mid is miscalibrated in a way a walk-forward recalibration fixes out of time. Those three numbers rank the In-game Model 2.0 candidates.

Corpus K (Kalshi, Sept): data/cache/ingame_capture_view_v2/kalshi/mlb/<date>.jsonl (series KXMLBGAME only; two tickers per game, one per team suffix) + data/cache/ingame_capture_view_v2/state/mlb/<date>.jsonl (live rows; final rows give the outcome). Shards 09-22..09-26 and 09-29 (09-29 games may be unsettled: exclude unsettled, count them).
Corpus P (Polymarket, Sept): data/cache/ingame_books_local/polymarket/mlb/<date>.jsonl (09-24..09-29; rows carry game_key; the moneyline slug is mlb-<away>-<home>-<date>, NOT the -player-props series; the home-team outcome token's best_bid/best_ask).
Corpus J (June-July, different games): data/cache/ingame_grade_joined/mlb_clean/*.jsonl (227 games, market_prob, state_summary, outcome, ts).

P1 probe_p1_event_response.py (corpora K and P; also run the same code on NFL capture_view_v2 state+kalshi KXNFLGAME for its 2 live games, descriptive only):
- Events from consecutive live state rows per game (sort by capture_ts): SCORE (score_home/score_away changed; sign +1 if home gained, -1 if away gained), OUT (outs increased within the same inning+half; sign -1 if home batting i.e. half Bottom, +1 if half Top). Record t_recv = capture_ts of the first row showing the change, t_play = state.last_play_ts if present, source_ts.
- Book series per game: home-team ticker yes mid (yes_bid+yes_ask)/2 from both snapshot and snapshot_bulk rows at their capture_ts; drop crossed/empty books (bid<=0 or ask>=1 or ask<bid) and count them. Report the live book receipt cadence (median / p90 gap between consecutive receipts per ticker while the game is live) and the median gap between mid CHANGES.
- Per event, with m(t) = as-of mid (latest receipt <= t): pre = m(t_recv) - m(t_play - 5 s) (if t_play missing use t_recv - 60 s and count), post_h = m(t_recv + h) - m(t_recv) for h = 5, 15, 30, 60, 120 s; all multiplied by the event sign. Also our feed lag t_recv - t_play (p50/p90).
- Report per event type and pooled: n_events, n_games, mean signed pre, mean signed post_h with game-clustered 95 pct CI, the post-receipt share = sum(signed post_120) / sum(signed pre + post_120), and the fraction of events whose book had NOT changed between t_play and t_recv. Also a fixed normal-approximation win-expectancy WE(state) (define it in the script with a-priori constants: runs per half-inning mean 0.5 and variance 1.0, current-half run expectancy from the standard RE24 base-out table, a tie to extras = 0.5, home/away remaining half-innings) and report the OLS slope of (signed total move) on |dWE|.
- Interpretation line to print: whether the post-receipt move is distinguishable from 0 (CI excludes 0) and its size in probability points.

P2 probe_p2_price_source.py (corpus K):
- Ticks = focus `snapshot` receipts of the home ticker while market_state == "live", subsampled to at most one per 30 s per game (first receipt in each 30 s bucket). Candidates at each tick, all as-of (no future data): MID (home yes mid), MICRO (microprice = (yes_bid * ask_size + yes_ask * bid_size)/(bid_size + ask_size) with bid_size = yes_bid_size, ask_size = no_bid_size; skip if sizes missing, count), LAST (latest trade yes_price_dollars on the home ticker at or before the tick, if within 300 s else missing), LAG (the previous receipt's mid), PAIR (the average of home mid and 1 - away-ticker mid, as-of the away ticker's latest receipt within 60 s).
- Score each vs the settled outcome: Brier and log loss, paired delta vs MID with game-clustered CI, n_games. Report the spread distribution (p50/p90 of yes_ask - yes_bid) and repeat the MID vs MICRO and MID vs PAIR deltas on the subset spread >= 0.03.

P3 probe_p3_mid_calibration.py (corpora K and J):
- Reliability of the mid: 10 equal-width bins (priced mean, realized mean, n_ticks, n_games per bin) and ECE, for all live ticks (K: the P2 ticks; J: every tick subsampled to one per 60 s per game) and for the late phase (inning >= 8).
- Extreme late bands (inning >= 8): mid < 0.10, 0.10-0.20, 0.80-0.90, > 0.90: priced mean vs realized, n_ticks, n_games.
- Out-of-time recalibration: fit on corpus J ONLY (all of it; June-July), apply to corpus K (Sept): (i) Platt on logit(mid); (ii) Platt on logit(mid) with a late-phase interaction (inning >= 7 indicator times logit(mid)); (iii) isotonic on mid. Paired delta vs raw mid on K with game-clustered CI. Also the reverse direction is not allowed (K is later in time). Additionally a within-J walk-forward by date (train on dates strictly before each scored date, first 5 dates burn-in) for (i)-(iii).
- Report ECE before/after on K.

Write all scripts, stdout copies and JSON outputs in the probe dir. Final report per PROBE_RAILS.md.
