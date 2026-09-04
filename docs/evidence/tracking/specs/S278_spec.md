GAP S278 | sport all (in-game) | worktree a14 | log cx_s278_pooled_power_rescreen
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: successor to S270 (still OPEN/queued in this repo's register; its v attempt-2 memo is not in main). Its
  feasibility table is taken from `C:/Users/neelj/nba-track-a16/docs/evidence/harness/` (attempt-2 files,
  worktree a16) and stated here, not re-derived: S06 shortfall 66,687.394 (req 66,914.394/avail 227), S117
  148,459.824 (148,467.824/8), S119 721.529 (762.529/41), S58_trial1 33,613.709 (33,840.709/227), S79 2,309.082
  (2,339.082/30), S80 8,893.091 (9,120.091/227), S82 535.529 (762.529/227), S84 1,084.498 (1,368.498/284). The
  three smallest shortfalls (most feasible) are S82, S119, S84. S270's own JSON names S82/S119's larger pool as
  `data/cache/ingame_grade_joined/mlb` (227 JSONL files, id_column game_id); it names S84's only larger candidate
  as `ingame_eval_cache.parquet` (1,987 game_id values) and documents it key/schema incompatible with S84,
  therefore not pooled. S270 already sealed and scored S82's pooled re-screen: 127 scored game clusters, Brier
  delta +0.004532110881, MDE80 0.008164580827 (SINGLE-WINDOW, still short of the required 762.529 n_eff).
PREMISE (step 0, INFORMATIONAL): confirm `data/cache/ingame_grade_joined/mlb` is present in this worktree and
  print its file count; reproduce S270's S82 pooled result above from its named archive if reachable, else print
  NOT FOUND; confirm `ingame_eval_cache.parquet`'s 1,987 game_id count and its documented S84 incompatibility.
CHANGE (step 1): for S82 and S119, seal a fresh prereg (LF; SHA-256 of staged bytes above the seal line) pooling
  the unchanged `data/cache/ingame_grade_joined/mlb` corpus into each screen's own unmodified feature/purge
  route, scored through scripts/platformkit/eval_gate/cpcv_engine.cpcv_evaluate with purge and a symmetric
  nonzero embargo; report new available clusters and MDE80 for each. For S84, since S270 already found no
  eligible larger pool, report REMAINS UNDERPOWERED at its existing 284-cluster MDE80 without inventing a pool.
  Never touches S270's, S82's, S119's, or S84's original artifacts (new dated filenames only); never flips a
  flag; never writes data/registry/.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = per-screen MDE80 and available game clusters, before (S270 table) vs after this row, for S82,
                  S119, S84
  before        = S82 762.529 required/227 avail (S270 pooled re-screen: 127 clusters, MDE80 0.008164580827);
                  S119 762.529 required/41 avail; S84 1,368.498 required/284 avail, no eligible larger pool
  bar           = MDE80 <= 0.004 achieved for each pooled re-screen; a screen not reaching it reports the
                  achieved MDE80 and is labelled REMAINS UNDERPOWERED, which is a valid success; any Brier
                  improvement found in a pooled re-screen is judged against the frozen +0.004 bar
  n             = >= 30 game clusters per re-screened screen, printed; S84 uses n = 284 (CONSTRUCT: its full
                  named corpus, no larger pool exists)
  eye check     = n/a (S-row); reproduction = verifier reruns each sealed re-screen and diffs every number
  must not move = S270's, S82's, S119's, S84's original artifacts; the +0.004 bar; backtest_fwer.jsonl untouched,
                  K unread, nothing charged
NON-TAUTOLOGY: MDE80 is computed from the full pooled n_eff each screen actually reaches, never from a subset
  chosen because it clears the bar; S84's REMAINS UNDERPOWERED verdict is reported even though it is negative.
EVIDENCE: docs/evidence/harness/S278_pooled_power_rescreen_2026-09-04.md + summary JSON + 2 paired-loss CSVs.
TEST: one per-file test recomputing one screen's required_n_eff formula and MDE80 from a small fixture.
REPORT: 3-screen before/after MDE80 table, RSS, test line, SHA. No push. NEVER PARK.
