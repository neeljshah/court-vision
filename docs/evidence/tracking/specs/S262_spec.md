GAP S262 | sport nba | worktree a17 | log cx_s262_boxscore_q50_census
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
CONTEXT: S243 CLOSED AT LIMIT (6c1af0488bd4b1f05e267c685b7d5291dc53f510). The one preregistered source,
  data/intelligence/matchup_grid.parquet (141,940 bytes, 4,900 rows, 2024-10-22..2026-04-12), lacks all seven
  required q50 fields (q50_minutes, q50_pts, q50_reb, q50_ast, team_q50_pts, team_q50_reb, team_q50_ast). This
  row censuses OTHER on-disk stores for per-player distributional quantiles/samples before naming the producer
  missing platform-wide.
PREMISE (step 0, INFORMATIONAL): reconfirm matchup_grid.parquet's 4,900 rows and absent q50 columns (one open,
  read-only). Then grep filenames only (never open a store over 300 MB) under data/cache/*, data/intelligence/,
  data/domains/ for stores whose column list names pts/reb/ast paired with a quantile/sample marker (q10/q50/
  q90, quantile, sample, distribution).
CHANGE (step 1): for each candidate store found, open ONE column at a time to confirm real quantile/sample
  columns, not just a name match; print the exact path, byte size, column list, and row count. If one store
  carries usable per-player PTS/REB/AST quantiles, rerun the S243 attempt-2 coherence check
  (scripts/platformkit/boxscore_dist_coherence.py) on real rows with a distinct 30-case matrix built from that
  store (never reuse the S243 fixture). If none exists, report CLOSED AT LIMIT naming every candidate store
  checked and why each failed -- a valid success, not a fix. Never write data/ or docs/research/; no src/
  kernel/ api/ intel/ edits.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = existence census of per-player distributional PTS/REB/AST sources; if found, minutes-sum and
                  stat-sum deviation per game from boxscore_dist_coherence.py on real rows
  before        = matchup_grid.parquet is the only store checked; it lacks all 7 q50 fields (S243)
  bar           = every candidate store's exact path/columns/row count printed; if a usable store exists, a
                  distinct 30-case real-row matrix scored with 0 silently excluded; else CLOSED AT LIMIT naming
                  the missing producer
  n             = 30 real cases (CONSTRUCT) if a store exists; else 0 (CLOSED AT LIMIT is the valid result)
  eye check     = n/a (S-row); reproduction = verifier reruns the column-level census and, if scored, the
                  checker
  must not move = the 240 + 5*OT minutes budget; the 0.6/0.5 and 0.3/0.3 verdict thresholds; boxscore_
                  crosscheck.py
NON-TAUTOLOGY: a store with only point predictions (not quantiles/samples) is named excluded, not passed as a
  match; a missing target stays EXCLUDED_MISSING_TARGET, never zero.
EVIDENCE: docs/evidence/harness/S262_boxscore_q50_census_2026-09-04.md plus the store census table and (if
  scored) the deviation table. ASCII only; calibration language only; evidence files under 50 MB.
TEST: one new per-file test (census logic on a synthetic store list; real-row matrix scoring if a store
  exists), run only that file.
REPORT: census table, verdict (store found + scored, or CLOSED AT LIMIT), test line, SHA. Commit by pathspec,
  no push. NEVER PARK.
