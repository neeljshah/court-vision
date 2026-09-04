GAP S209 | sport mlb (in-game) | worktree a18 | log cx_s209_mlb_phase_recal_fwer
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: S88_phase_recal_2026-09-04.md section 4, verbatim: "this is 15 buckets scored NO_CHANGE / IMPROVED (1) /
WORSE (1) with no multiple-comparison correction applied (see NOT VERIFIED) -- read bucket-by-bucket, not as a single
verdict." So the one in-game effect with a CI excluding zero (late|leading_big +0.031643 [0.0088, 0.0572]) has no
family bar and no second corpus; its sibling mid|trailing -0.011964 WORSE has the same status. Q5 wants a second unit.
PREMISE (step 0): re-measure and print from the S88 archive: pooled 33,920 eval ticks / 11,087 informative / 127 games
/ n_eff 179.8, incumbent 0.174603 vs recal 0.176080 vs market 0.170853, delta -0.002890 [-0.0114, 0.0052];
late|leading_big 2,084 / 349 / 50 games, 0.037098 -> 0.028937, +0.031643 [0.0088, 0.0572]; mid|trailing 2,383 / 963 /
66 games, 0.161531 -> 0.157551, -0.011964 [-0.0232, -0.0010]; denominator 47,104 ticks / 158 games. If any fails to
reproduce, STOP, memo, commit, FALSIFIED.
LIMIT (step 1): count the disjoint corpus_units the MLB store can supply for a replication (ISO-week partition sides;
MLB window 2 if S55 has reached 30 games). With only one unit the two S88 bucket verdicts are labelled SINGLE-WINDOW
-- never an AHEAD, never a lowered floor.
CHANGE (step 2): smallest additive change -- apply BH at q = 0.05 across the enumerated 15-bucket family to the
archived per-bucket deltas, and re-score the same two SPECS on the second unit if step 1 found one. No refit of the
incumbent, no new bucket definition. Additive only, nothing renamed; helper <= 300 lines within
test_loc_rail_scope.py; never write data/; no flag on; no edits in src/ kernel/ api/ intel/ scripts/team_system/; one
store at a time, never > 300 MB; never touch register or ledger.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = per bucket: the S88 delta, its raw p, its BH-adjusted p at q = 0.05 over the 15-bucket family, and
                  the second-unit delta with its own game-clustered CI where a second unit exists; denominator = the
                  enumerated 15 buckets over 33,920 eval ticks / 127 informative game clusters
  before        = 15 buckets with raw CIs and NO correction: 1 IMPROVED, 1 WORSE, 13 NO_CHANGE, pooled NO_CHANGE
  bar           = 15 of 15 buckets carry a BH-adjusted p and a replication label (REPLICATED / NOT REPLICATED /
                  SINGLE-WINDOW), the three quoted S88 figures reproduce at max abs diff <= 1e-9, and any bucket
                  losing its label under BH is reported as losing it. late|leading_big failing BH is the expected
                  valid result
  n             = 15 (CONSTRUCT: every bucket the S88 partition produces, exhaustively enumerated), with per-bucket
                  clusters
  eye check     = n/a (S-row); reproduction = the verifier recomputes the 15 deltas, the BH adjustment and any
                  second-unit delta from the archived per-game paired-loss series alone
  must not move = bucket_recalibration.py SPECS, the S88 artifact and its archived series byte-identical, every
                  eval_gate threshold, backtest_fwer.jsonl untouched, K unread; the MLB hedge trial's standing BEHIND
NON-TAUTOLOGY: all 15 buckets enter the BH family, including the 13 NO_CHANGE ones. Adjusting over only the buckets
with a CI excluding zero is exactly the error this row exists to fix -- REJECT.
EVIDENCE: docs/evidence/harness/S209_mlb_phase_recal_fwer_2026-09-04.md -- the 15-row BH table, the replication
column, the three reproduction diffs, a NOT VERIFIED list, summary JSON (Q9).
TEST: scripts/platformkit/ingame/test_s209_phase_recal_fwer.py -- one new per-file test; run only that file.
REPORT: the BH table, survivors, replication labels, test line, SHA. Commit by pathspec, no push. NEVER PARK.
