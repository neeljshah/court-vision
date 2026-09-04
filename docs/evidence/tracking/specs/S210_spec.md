GAP S210 | sport all (in-game) | worktree a15 | log cx_s210_ingame_power_audit
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: memory note ingame_signals_first_2026_09_03, verbatim: "MLB in-game: every screen is NULL by construction at
41 game-clusters (CI half-width ~0.005 > the 0.004 bar)". Register row S93 agrees, CLOSED AT LIMIT. Yet the standing
screens (S80, S82, S84, S94, S96, S97, S99-S103, S114-S117, S119, S123) are recorded NULL / NEGATIVE with no power
statement, so the program cannot tell a refuted hypothesis from an unmeasurable one.
PREMISE (step 0): enumerate by grep every docs/evidence/harness memo carrying an in-game screen verdict with a numeric
improvement AND a CI, list them with n_ticks, n_game_clusters and n_eff, and reproduce two anchors: S82's
tick_index_in_game +0.003332 CI [-0.001971, +0.008636] on 15,702 ticks / 41 clusters, and S117's soccer screen on 163
ticks / 2 clusters. If either fails, STOP, memo, commit, FALSIFIED.
LIMIT (step 1): this row computes NO new model and changes NO verdict. It reports per screen the minimum detectable
Brier delta at 80 pct power from that screen's own archived series and clustered n_eff. A screen with no series is NO
SERIES ARCHIVED: out of the power column, never the enumeration.
CHANGE (step 2): smallest additive change -- one read-only auditor under scripts/platformkit/eval_gate/ that reads
each archived series, computes the paired-loss standard error and the 80 pct-power MDE, and emits a table; it writes
no verdict into any existing artifact. Additive only, nothing renamed; helper <= 300 lines within
test_loc_rail_scope.py; never write data/; no flag on; no edits in src/ kernel/ api/ intel/ scripts/team_system/; one
store at a time, never > 300 MB; never touch register or ledger.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = per screen: n_ticks, n_game_clusters, n_eff, observed improvement, observed CI half-width, the 80
                  pct-power minimum detectable Brier delta, and the label UNDERPOWERED (MDE above the frozen +0.004
                  bar) or REFUTED-AT-BAR (MDE at or below); denominator = the printed enumerated count
  before        = 0 -- no in-game screen on record carries an MDE or a power label; S93 states the constraint for one
                  corpus only and no memo generalises it
  bar           = every screen appears with all seven quantities or an explicit NO SERIES ARCHIVED reason, the two
                  premise anchors reproducing at max abs diff <= 1e-9, 0 screens silently omitted. A finding that most
                  standing NULLs are UNDERPOWERED rather than refuted is expected; no existing verdict is edited
  n             = the enumerated screen count (CONSTRUCT: every in-game screen memo with a numeric improvement and a
                  CI, exhaustiveness proved by the printed grep and its file list)
  eye check     = n/a (S-row); reproduction = the verifier reruns the grep, checks the file list matches, and
                  recomputes the MDE for three rows chosen EVENLY across the sorted table from their own series
  must not move = every existing memo and artifact byte-identical (this row appends nothing); the frozen +0.004
                  in-game bar; every eval_gate threshold; backtest_fwer.jsonl untouched, K unread
NON-TAUTOLOGY: enumeration is by grep over all in-game memos, not the auditor's convenience. Dropping the screens
whose series are missing from the DENOMINATOR, not just the power column, is circular -- REJECT.
EVIDENCE: docs/evidence/harness/S210_ingame_power_audit_2026-09-04.md -- the enumerated table, the grep and its file
list, the two anchor reproductions, a NOT VERIFIED list, summary JSON (Q9).
TEST: scripts/platformkit/eval_gate/test_s210_power_audit.py -- one new per-file test; run only that file.
REPORT: screens enumerated, UNDERPOWERED vs REFUTED-AT-BAR counts, test line, SHA. Commit by pathspec, no push. NEVER
PARK.
