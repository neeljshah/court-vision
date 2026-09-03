GAP S157 | sport mlb+soccer | worktree a13 | log cx_s157_game_key_rekey
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- self-check section B and Q (S-row) before reporting.
PREMISE (step 0): event_key is market-type-specific -- reproduce 2026-09-04: 0/3,932 MLB and 0/288 soccer_intl event_key groups carry >=2 market types. The series-prefix strip (`event_key.split("-",1)[1]`, per `rekey_market_overlap` in scripts/platformkit/ingame/s90_microstructure_screen.py) yields MLB moneyline+total on 99 of 3,792 game suffixes (2.61pct) and soccer_intl all three markets on 96/96 (S90 2026-09-04). If these do not reproduce, STOP, write the memo, report FALSIFIED.
LIMIT (step 1): apply the ONE stated strip rule to every row of both stores (not a hand-picked subset) and count games with >=2 market types under the new key; report the number even if below 99/96. If the generic rule undercounts vs S90's ad-hoc numbers, STOP and report CLOSED AT LIMIT.
CHANGE (step 2): in scripts/platformkit/venue_history/build_price_series.py add ONE new opt-in function `add_game_key(frame) -> frame` (adds a `game_key` column = the one strip rule applied to `event_key`; `event_key` untouched) and a new writer path/flag emitting `data/cache/inplay_odds/<sport>_price_series_gamekeyed.parquet`. Never rewrite the landed `{mlb,soccer_intl}_price_series.parquet` in place; every existing reader stays untouched.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = games carrying >=2 market types under game_key / games enumerated per sport (denominators: MLB 3,792 game suffixes, soccer_intl 96 games)
  before        = 0/3,792 MLB, 0/96 soccer_intl under event_key (measured 2026-09-04)
  bar           = 99/3,792 MLB and 96/96 soccer_intl under game_key from the ONE stated rule applied uniformly -- or the honest lower measured number; never a targeted number
  n             = 5 (CONSTRUCT) -- synthetic frame: one game with moneyline+total+spread rows must re-key to a single game_key carrying all 3 market types
  eye check     = n/a (S-row); reproduction = re-run add_game_key() on the real parquet stores and recount matches per sport
  must not move = event_key column, every existing reader of {mlb,soccer_intl}_price_series.parquet, all harness thresholds, the FWER ledger
NON-TAUTOLOGY: the strip rule is stated once and applied to every row of both stores, not only the 99/96 rows that already match -- a rule special-cased to hit the bar is a REJECT, report it yourself.
EVIDENCE: docs/evidence/harness/S157_game_key_rekey_2026-09-04.md -- before/after table, exact denominators, CONSTRUCT test output, NOT VERIFIED list.
TEST: exactly one new per-file test (CONSTRUCT, n=5) -- `python -m pytest scripts/platformkit/venue_history/test_build_price_series.py -q`.
POD: none needed -- local parquet only.
COMMIT: explicit pathspec, in the worktree, no push. Report the sha.
NEVER PARK: poll to completion this turn; never end waiting.
Calibration language only (Q6): no dollar/ROI/edge word; report honestly if the generic rule underperforms 99/96 (REJECT/CLOSED AT LIMIT are successes).
