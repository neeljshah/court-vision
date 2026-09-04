GAP S240 | sport all | worktree a17 | log cx_s240_boxscore_prop_census
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
CONTEXT: BOX_SCORE_PROGRAM_2026-09-04.md section (a) lists prop-line stores but only NBA's 77-file
count was reproduced live; MLB/tennis prop_history_corpus_*.jsonl (3,000 rows each) were sampled on
one row only (market_prob null) and soccer's is 0 rows. No single census exists across all four.
PREMISE (step 0): for each sport (nba, mlb, soccer, tennis) report: prop-line store path, exact row
or file count, distinct players, distinct stat names, date range, and the count of rows/files
carrying a non-null real market price (not a synthetic/None field). Use wc -l / parquet metadata /
JSON file counts only -- never load a store fully into memory.
LIMIT (step 1): for each sport, state SCORABLE (>= 30 game clusters with a real market price) or
NOT SCORABLE (name the exact blocking count) -- do not fit anything to a NOT SCORABLE sport.
CHANGE (step 2): additive only -- new module scripts/platformkit/boxscore_prop_census.py emitting
one JSON per sport with the counts above plus a combined summary table.
RAILS: one store at a time, never over 300 MB; never write under data/; never touch the register or
the FWER ledger; no edits under src/ kernel/ api/ intel/ scripts/team_system/ or token-gated
eval_gate modules (PROPOSED snippets in docs/research/ instead); new helpers <= 300 lines.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = per-sport row/file count, distinct player count, distinct stat count, non-null
      real-market-price count, reproduced from a fresh script run
  before        = no cross-sport census exists; NBA 77 files and MLB/tennis 3,000/3,000 rows /
      soccer 0 rows are the only counts on record, each measured separately
  bar           = all four sports present in one JSON with 0 unparsed files/rows and an explicit
      SCORABLE/NOT SCORABLE verdict per sport with its blocking count named
  n             = 4 sports (CONSTRUCT)
  eye check     = n/a (S-row); reproduction = the verifier re-runs the census script and diffs the
      per-sport JSON byte-for-byte on row/file counts
  must not move = every source file/store (read-only); the closing_props JSONs; the jsonl corpora
NON-TAUTOLOGY: the census counts every file/row including ones with a null market price; a
SCORABLE verdict on a sport whose real-market-price count is the thing making it scorable must
print that count, not just the raw row count.
EVIDENCE: docs/evidence/harness/S240_boxscore_prop_census_2026-09-04.md plus the per-sport JSONs.
ASCII only, calibration language only; a NOT SCORABLE verdict on any sport is a success.
TEST: one new per-file test (a small fixture directory with a mixed null/non-null market price
column parses to the correct SCORABLE/NOT SCORABLE verdict), run only that file.
REPORT: the 4-sport table, each verdict with its n, the test line, SHA. Commit by pathspec, no
push. NEVER PARK.
