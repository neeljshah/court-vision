GAP S203 | sport all (harness) | worktree a15 | log cx_s203_replication_wiring
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: docs/evidence/harness/S08_replication_gate_2026-09-03.md:42, verbatim: "NEW GAP: stacker.py emits
min_corpora_eff + single_window=True but does not apply replication_verdict to its own AHEAD, and hard-codes
n_corpora=1 rather than counting disjoint corpus_units." Its :106 names the AHEAD writers left unwired:
ingame/mlb_winprob_v6.py (:105, :186-187), ingame/mlb_winprob_v7.py (:179), frontend/slate.py (:80),
pm_trading/clv_daily_readout.py (:117), eval_gate/stacker.py (:224), all under scripts/platformkit/. Q5 is
still a memo convention at five of six writers, so a single-window result can keep an AHEAD label.
PREMISE (step 0): re-measure and print on a clean tree: stacker.py:224 computes
`"AHEAD" if (improvement >= BAR and dm.ci95[0] > 0.0 and p_defl < 0.05) else "BEHIND"` and emits
single_window=True with n_corpora literally 1; replication_gate.py (S08, e54e1faf0) is wired at exactly ONE
call site (hedge_trial_runner), construct bar 2/2 at K=14; the other five writers still emit an AHEAD with
no downgrade. Confirm all six paths and line numbers exist. If falsified, STOP, memo, commit, FALSIFIED.
LIMIT (step 1): no real AHEAD exists to downgrade today (the MLB hedge trial stands BEHIND, single-window,
K=14), so this is a CONSTRUCT wiring row that can never close on a live firing. State per writer whether
its AHEAD branch is reachable at all; an unreachable branch is wired and labelled, never a live pass.
CHANGE (step 2): the smallest additive change -- call the existing replication_verdict at each of the five
unwired writers so an AHEAD with n_corpora below the floor is emitted as SINGLE-WINDOW, counting disjoint
corpus_units where a corpus_unit column exists (else take an explicit count; never inherit the constant 1).
Additive only: the raw verdict keeps its key and value and the downgrade is a NEW key; nothing renamed or
removed; every reader of each touched key grepped and named (A5); new helper <= 300 lines, inside
tests/platformkit/test_loc_rail_scope.py counts; never write under data/.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = AHEAD writers that downgrade an AHEAD to SINGLE-WINDOW when n_corpora is below
                  min_corpora_eff, over the enumerated denominator of 6 writers (5 above + hedge_trial_runner)
  before        = 1 of 6 (hedge_trial_runner only, S08 e54e1faf0)
  bar           = 6 of 6, each proved by two cases -- n_corpora=1 downgrades to SINGLE-WINDOW, n_corpora=2
                  leaves AHEAD unchanged -- and every pre-existing output key byte-identical in value and name
  n             = 12 (CONSTRUCT: 6 writers x 2 cases, exhaustively enumerated)
  eye check     = n/a (S-row); reproduction = the verifier runs the 12 cases itself in master and greps every
                  named reader of each touched artifact key
  must not move = min_corpora_eff and every eval_gate threshold; the MLB hedge trial's standing BEHIND;
                  hedge_trial_2026-09-01.json NOT regenerated; backtest_fwer.jsonl untouched with K unread
NON-TAUTOLOGY: all six writers are enumerated by path and line and none is excluded. A writer that "passes"
only because its AHEAD branch is unreachable must be named as such in the table, not counted as a live pass;
counting only the reachable writers to reach 6 of 6 is circular -- report REJECT yourself.
EVIDENCE: docs/evidence/harness/S203_replication_wiring_2026-09-04.md -- the 6-writer table, the 12 construct
cases, the reader grep per artifact key, and a NOT VERIFIED list; copy the case output under docs/evidence/.
TEST: scripts/platformkit/eval_gate/test_s203_replication_wiring.py -- one new per-file test; run only it.
REPORT: 6-writer table, 12/12 cases, diff stat, test line, SHA. Commit by pathspec, no push. NEVER PARK.
