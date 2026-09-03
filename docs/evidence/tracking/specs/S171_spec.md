GAP S171 | sport mlb+nba | worktree a18 | log cx_s171_period_grain_premise
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
CONTEXT (register row S73): two frozen families have no matching corpus and were screened on the wrong market --
mlb_inning (period/total) and nba_quarter_shape (period/spread) were scored on the ML / over-2.5 gate corpora
and are flagged in the promotion list as market-label mismatch. The two honest ways out are (1) build period-grain
corpora or (2) drop the families from the frozen spec (a versioned spec change, orchestrator/user decision).
This lane does the PREMISE CHECK for (1) only: does the data to build a period-grain corpus exist on local disk?
PREMISE (step 0), read-only, exact counts, one file at a time, no local load over ~300 MB (read columns, not
whole stores; subsample and say so):
  (a) MLB inning grain: which local stores carry per-inning scores or per-inning market lines with timestamps
      (data/cache/inplay_odds/mlb_price_series.parquet market types; data/cache/ingame_grade_joined/mlb;
      data/domains/mlb/** as-of tables with inning columns)? Count games with (i) per-inning state, (ii) a period
      total/spread line, (iii) both -- with denominators; date range.
  (b) NBA quarter grain: same for quarter state + quarter spread/total lines (data/cache/eval_gate/
      nba_checkpoints_full.parquet is NOT junctioned here -- report its absence rather than guess;
      data/domains/basketball_nba/** and data/cache/inplay_odds/nba* if present).
  (c) For each family, read its frozen definition (scripts/platformkit/foundry FWER_FAMILIES_SPEC / grammar) and
      state exactly which columns the family expects and which of them the stores in (a)/(b) can supply.
LIMIT (step 1): if a family has fewer than 30 games with BOTH state and its period-market line, the corpus
cannot meet the n >= 30 rail today -> report the count as the LIMIT; do not build.
CHANGE (step 2): NO code, NO corpus build. The deliverable is the premise memo with a decision table:
  family | state games | period-line games | both | date range | columns missing | verdict (BUILDABLE n>=30 /
  NOT BUILDABLE today / DECISION: drop from the frozen spec).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = families with a complete decision row / 2
  before        = 0 / 2
  bar           = 2 / 2 with exact denominators and file paths; 0 fabricated counts; a NOT VERIFIED list
  n             = 2 families (CONSTRUCT); game counts are measured, not sampled
  eye check     = n/a (S-row); reproduction = the verifier re-runs the two count commands from the memo
  must not move = every store, every threshold, the frozen spec, the FWER ledger (never touched)
NON-TAUTOLOGY: both families reported whatever the verdict.
EVIDENCE: docs/evidence/harness/S171_period_grain_premise_2026-09-04.md -- the decision table, the exact
commands, NOT VERIFIED list. ASCII only. Calibration language only.
TEST: none (measurement memo only); do not add a test that reads the stores.
COMMIT: explicit pathspec in the worktree (memo only), no push. Report the sha. NEVER PARK; finish with the
report + SHA.
