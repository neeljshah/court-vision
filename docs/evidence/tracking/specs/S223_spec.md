GAP S223 | sport all | worktree aXX | log cx_s223_intel_pool_asof_census
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
CONTEXT: the intelligence pool has never been inventoried with grain, rows and AS-OF SAFETY. Measured 2026-09-04
(INTELLIGENCE_SIGNALS_PROGRAM_2026-09-04.md section 1): 8 of 45 data/cache/atlas_*.parquet stores sampled evenly carry
a SINGLE as_of 2026-05-31 (min == max), while ~14 data/intelligence/ sidecars carry a per-row game_date/asof_date
(momentum_signals 673,204 rows; player_def_archetype_sidecar and player_opp_splits_sidecar 99,498 each;
confidence_ensemble and per_player_calibration 307,643 each). Every later family's leak-freeness depends on which half
it draws from and no artifact records the split.
PREMISE (step 0): re-measure the as_of cardinality of ALL 45 atlas stores and of every data/intelligence/ parquet, ONE
FILE AT A TIME. Confirm or falsify the sampled finding; if any atlas store carries more than one distinct as_of,
report the exact count. Recount: of the 1,593 games in data/cache/inplay_odds/nba_checkpoints_full.parquet, how many
have game_date after the atlas as_of (measured 5, 915 ticks).
LIMIT (step 1): if the snapshot-only share is what it appears, no walk-forward join to those stores is possible at
all; the deliverable is then the labelled census plus the named producer of each snapshot store -- CLOSED AT LIMIT for
the atlas half, not a failure.
CHANGE (step 2): additive only -- one new module under scripts/platformkit/ that walks a declared path list and emits
a census table (path, rows, n_cols, grain key columns, n distinct as_of, min/max date, AS-OF SAFE / SNAPSHOT-ONLY /
UNDATED, producer module or NONE) plus a JSON. No store is rewritten and no producer is run.
RAILS: one store at a time, never over 300 MB; never write under data/; never touch the register or the FWER ledger;
no edits under src/ kernel/ api/ intel/ scripts/team_system/ or the token-gated eval_gate modules (PROPOSED snippets
in docs/research/ instead); new helpers <= 300 lines (LOC rail).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = census rows emitted per path declared, and n distinct as_of per store
  before        = 8 of 45 atlas stores sampled carry exactly 1 distinct as_of (2026-05-31); 5 of 1,593 checkpoint
      games post-date it
  bar           = all 45 atlas stores plus every present data/intelligence/ parquet enumerated, 0 skipped and 0
      unreadable without a printed reason; each carries a label; the 5-of-1,593 count reproduces exactly; every
      SNAPSHOT-ONLY store names its producer module or the string NONE
  n             = 45 atlas + every present data/intelligence/ parquet (CONSTRUCT)
  eye check     = n/a (S-row); reproduction = the verifier re-runs the census module and diffs the JSON
  must not move = every data file (read-only pass); every threshold; the FWER ledger; the register
NON-TAUTOLOGY: the census covers every declared path including empty and unreadable ones; a store excluded for any
reason is listed with that reason, never dropped silently.
EVIDENCE: docs/evidence/harness/S223_intel_pool_asof_census_2026-09-04.md plus the census JSON. ASCII only,
calibration language only; an honest NULL, REJECT or CLOSED AT LIMIT is a success.
TEST: one new per-file test for the census module (labels, plus a synthetic single-as_of store), run only that file.
REPORT: the SAFE / SNAPSHOT-ONLY / UNDATED counts, the 5-of-1,593 recount, the test line, SHA. Commit by pathspec, no
push. NEVER PARK.
