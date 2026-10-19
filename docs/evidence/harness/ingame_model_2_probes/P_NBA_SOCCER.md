PROBE TASK P5-P6: NBA market-anchored state projection (Polymarket, 1,593 games, two seasons) and soccer after-goal response

Read PROBE_RAILS.md (same dir) first; it is binding. Then the schema card.

Context: on NBA, every prior residual/recalibration of the Polymarket in-play price trailed the price (S115, S272, S277, S281, S283 in docs/evidence/harness). None tested the specific mechanism "the price is STALE (no trade since a score change), so project the last traded price forward through the state change while keeping the market's implied team strength". S277 found the mid's age p50 600 s on this corpus, so staleness is common.

Corpus N: data/cache/ingame_grade_joined/nba_checkpoints_r1/*.jsonl (1,593 game files named by sha256; manifest.json maps them; 465,249 rows; fields ts, market_prob, traded (bool), seconds_since_last_trade, state_summary "home_score=.. away_score=.. quarter=.. seconds_remaining=..", outcome, side, game_id, market_ticker). FIRST establish, and print, what market_prob is on non-traded ticks (does it change without a trade? is it a last-trade price or a mid?), and what seconds_remaining means (game seconds remaining of 2880? check quarter vs value), and how overtime appears. Split into two corpora by season: 2024-25 (ts before 2025-08-01) and 2025-26 (after).

P5 probe_p5_nba_projection.py:
- WP(margin, s_rem, mu) = Phi((margin + mu * s_rem/2880) / (sigma * sqrt(max(s_rem, 1)/2880))), home perspective, sigma FIXED a priori at 13.0 points (NBA final-margin SD scale; say so); overtime: treat s_rem as the OT remaining seconds with the same formula and count OT ticks separately.
- Anchor: at the last tick where traded == True (as-of, strictly <= current tick), invert market_prob to mu using that tick's state. PROJ = WP(margin_now, s_rem_now, mu). PROJ == market_prob when the state has not changed since the anchor. Clip mu to a sane range and count clips; skip anchors with market_prob outside (0.005, 0.995) and count.
- Scored ticks: every tick, and the STALE subset (state changed since the anchor). Compare PROJ vs market_prob: Brier, log loss, paired delta with game-clustered CI, n_games, n_ticks, per season and pooled, and per quarter (1-4, OT). Also bucket by seconds since the anchor (0-30, 30-120, 120-600, >600 s).
- Sigma sensitivity WITHOUT outcome snooping: choose sigma on the 2024-25 season only from the grid {10, 11.5, 13, 14.5, 16} by Brier of PROJ, then score 2025-26 with that sigma (report which sigma won). The fixed 13.0 run is the primary.
- Direction check: on stale ticks, the next traded market_prob change (signed by sign(PROJ - market_prob)): mean, CI, and correlation of (PROJ - market_prob) with the next traded change.
- A walk-forward shrink: logistic on [logit market_prob, logit PROJ - logit market_prob] trained on season 1, scored on season 2: coefficient and paired delta vs market_prob.

P6 probe_p6_soccer_goal_response.py (corpus data/cache/ingame_grade_joined/soccer_intl/*.jsonl, 51 World Cup games, fields ts, market_prob, state_summary "home_score=.. away_score=.. minute=..", outcome):
- Descriptive only (INSUFFICIENT expected): tick cadence (median gap), per goal event (score change between consecutive ticks) the signed market_prob change at that tick and over the next 1/2/5 ticks, the fraction of the total move already present at the first tick showing the goal. Also Brier of market_prob by minute band (0-30, 30-60, 60-75, 75-90+) and the late draw behaviour: for ticks minute >= 80 with a level score, priced vs realized home-win rate.

Write scripts/outputs in the probe dir. Final report per PROBE_RAILS.md.
