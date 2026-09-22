GAP S360 | sport nba | worktree harness-h18 (master-based) | log cx_s360_nba_joined_corpus
# NBA checkpoint corpus -> joined JSONL corpus for the four-arm scorer (the SECOND powered corpus: 1,593 games)

SINGLE PROBLEM: the sealed four-arm baseline has ONE powered corpus (MLB revision 3), so no AHEAD conclusion can ever be drawn
(two independent corpora are required). data/cache/inplay_odds/nba_checkpoints_full.parquet holds 465,249 ticks / 1,593 games
(2024-10-22..2026-06-13; columns game_id, game_date, ts (unix), period, game_clock_s, score_home, score_away, margin, market_prob,
traded, market_ticker, outcome_home_win, venue) -- price and state per tick, but NO model probability column and not in the joined
JSONL shape the scorer reads (scripts/platformkit/ingame/baseline_four_arm_eligibility.py: game_id, ts, market_prob, model_prob,
outcome, close_ts, state_summary with NBA features score_diff, quarter, seconds_remaining).

BINDING BEFORE-CONDITION (re-run, quote): `ls scripts/platformkit/ingame/nba_checkpoints_to_joined.py` fails. Locate the as-of NBA
model side that ledger row S86 created ("EVERY NBA IN-PLAY TICK NOW CARRIES A MODEL SIDE"): grep docs/evidence/RESULTS_LEDGER_SYSTEM.md
for "S86" and read the memo it names; quote the archive path and its columns. If that archive cannot be identified from tracked
files, say so and build the converter with model_prob as a REQUIRED input column supplied by a caller-given parquet/JSONL path.

CHANGE (NEW files only):
1. scripts/platformkit/ingame/nba_checkpoints_to_joined.py (<= 300 LOC; pyarrow streaming in row groups, never the whole table in
   memory; < 600 MB RSS): CLI `--checkpoints <parquet> --model-side <path> --out-dir <dir> [--check]`. One JSONL file per game under
   <out-dir>/nba_checkpoints_r1/, rows in ts order: sport "nba", game_id, ts as a timezone-aware ISO string, market_prob, model_prob,
   outcome (1.0 / 0.0 from outcome_home_win), side "home", close_ts = the game's last tick ts, state_summary =
   "home_score=<h> away_score=<a> quarter=<period> seconds_remaining=<game_clock_s converted to seconds left in the GAME>" (state
   the conversion rule; period > 4 is overtime), plus traded and market_ticker carried unchanged. The model side is joined by
   (game_id, ts) EXACTLY; a tick without a model value is written with model_prob null (the scorer excludes it and counts it) --
   never forward-filled, never interpolated. NO feature may be derived from outcome_home_win or any later tick.
   STALE-PRICE FIELD: carry `traded` and add seconds_since_last_trade when derivable from the series (a known artifact: an NBA
   mid-band cell was 97 pct stale ticks); do not filter -- the prereg decides populations.
   Writes a manifest {"files": {name: sha256}} in canonical compact JSON and a conversion census (games, ticks, ticks with a model
   value, ticks per period, first / last date). `--check` prints the census and writes nothing.
2. tests/platformkit/ingame/test_nba_checkpoints_to_joined.py: synthetic parquet + model side -- exact join only, null when absent,
   clock conversion incl. overtime, ordering, close_ts, no outcome-derived field, manifest hash stability, --check writes nothing;
   and feed the converter's output through baseline_four_arm_eligibility.select_rows(rows, "nba_checkpoints") to prove the scorer
   accepts the shape (eligible ticks > 0 on the fixture).
3. Memo docs/evidence/harness/S360_nba_joined_corpus_2026-09-21.md with the exact finisher command on the main data tree.

CONTROLS: PREPARE only; the builder has no data/ and runs nothing real; no calibration number. ACCEPTANCE: per-file test passes;
`--help` works; diff = NEW files only. Vocabulary follows contract Q6; automated scan required; assemble retracted-figure literals
from single digits. Memo ends with a NOT VERIFIED list. The pod is OFF.
