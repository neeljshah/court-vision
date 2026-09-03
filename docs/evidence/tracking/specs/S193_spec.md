GAP S193 | sport nba | worktree aXX | log cx_s193_teacher_census
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- self-check B1-B10 and Q1-Q9 before reporting.
PREMISE (step 0): re-measure and print all of it. data/tracking = 408 dirs + 15 loose files, only 393 match
^00\d{8}$ -- adopt the S69/S77 guard: SKIP a non-conforming name, never alias (a sport-blind MLB run
mlb_2iosUkpL0Bc lives there). Census over the 408: possessions.csv >200B 337, ball_tracking 353, events_log
344, features 7, game_context 4, manifest.json 4. gate_corpus_nba.parquet = 1,814 rows, 2024-10-22..2026-04-12,
y mean 0.5430; event_id format identical, no bridge needed. 207 of 393 join; 180 of those carry a non-trivial
possessions.csv (y 0.5222, 2025-01-23..2026-04-12) = 24,456 possession rows, 22,199 pbp_matched (90.77 pct), 172 games with >= 1 match. Falsified -> STOP, memo, report FALSIFIED.
LIMIT (step 1): a same-game vector is a leak by construction, so only AS-OF PRIOR GAME is usable. team_abbrev
is exactly 2 abbrevs in all 180 files (30 teams); ordered by event_date, 158 of 180 have BOTH teams with an
earlier tracked game and 172 have at least one. 158 clears student_gate.py:36-37 (_MIN_N_EFF 30.0,
_MIN_CLUSTERS 20). Below 20 clusters -> CLOSED AT LIMIT, do not fix.
CHANGE (step 2): one new module under scripts/platformkit/ writing ONE new parquet -- one row per
as-of-eligible event_id with its gate keys and the prior-game aggregates of drive_attempts, shot_attempted,
avg_defensive_pressure, avg_spacing, avg_vel_toward_basket, each printing its own covered-possession
denominator and covered-game count. fast_break EXCLUDED by name: within-game sd > 0 in only 45 of 180 games (median 0.00). Additive only; read-only on every input.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric = as-of prior-game teacher rows written, denominator = the 1,814 rows of gate_corpus_nba.parquet;
    plus per-column covered-fraction pass counts at 0.10 / 0.25 / 0.50 for the five kept columns
  before = 0 (student_gate.py 217 LOC has never run on a real corpus; nothing under docs/evidence/
    aggregates data/tracking to a game grain)
  bar = exactly 158 as-of rows (172 one-team, 180 joined) AND the census reproduces exactly: 408 / 393 / 337
    / 353 / 344 / 7 / 4 / 4, 1,814, 207, 180, 24,456, 22,199 (90.77 pct), 172, nonnull 7,868 / 7,868 / 7,505
    / 7,084 / 4,362, medians 0.254 / 0.254 / 0.254 / 0.241 / 0.139. Any miss -> CLOSED AT LIMIT with the
    exact shortfall; never lower a number.
  n = 158 (clusters/games, >= 30)
  eye check = n/a (S-row); reproduction = re-run the module, diff its printed census and its 158 against the memo table -- every figure exact
  must not move = student_gate.py, gate_corpus_nba.parquet, every file under data/tracking and
    data/cache/eval_gate/backtest_fwer.jsonl byte-identical; no ledger row charged, K unread, no flag ON
NON-TAUTOLOGY: covers the 180 joined events. EXCLUDES the 186 id-shaped dirs with no gate row, the 27 joined
dirs with no non-trivial possessions.csv, the 15 non-game names, the 22 events with no prior tracked game, the
7 frame-grain features.csv (headers 157/158/96/96/158/139/139; 0022400852 is ragged -- "Expected 96 fields in
line 15440, saw 148"), and fast_break. Those exclusions are WHY the count is 158 and not 180 -- naming is the row.
EVIDENCE: docs/evidence/harness/teacher_census_2026-09-04.md -- census table, per-column denominators, the
0.10/0.25/0.50 pass counts, a summary JSON copied under docs/evidence/, and a "NOT VERIFIED" list.
SCOPE: input census ONLY -- no Brier, no promotion, no "tracking improved a model" claim; the leak contract
turning these aggregates into an as-of predictor is the explicitly named NEXT gate. Calibration language only.
TEST: exactly one new per-file test; run only that file. <= 300 LOC per file.
COMMIT: explicit pathspec, in the worktree, no push. Report the sha.
NEVER PARK: poll your own jobs in a blocking loop; never end waiting.
