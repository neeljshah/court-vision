"""domains.mlb.ingame.rung8_state -- MLB evolving in-game state (edge queue item 1, rung 8).

Reconstructs live bullpen-usage state from data/domains/mlb/gumbo_live/<game_pk>.jsonl
GUMBO diff ticks. `bullpen_used` is not a field in the tick schema (schema comment
only), but it IS reconstructible: each tick already carries `pitcher_id` (the pitcher
currently on the mound) and `pitcher_pitches` (that pitcher's own cumulative pitch
count, resets to 0 on a change) at 100% coverage. See rung8_state.py docstring for the
hand-verification against the real boxscore pitcher order.

ACCURACY/CALIBRATION ONLY -- NO MARKET EDGE CLAIMED.
"""
