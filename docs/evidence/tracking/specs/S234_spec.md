GAP S234 | sport all | worktree aXX | log cx_s234_signal_factory_screen_verdict_partition
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
CONTEXT: REDTEAM_SIGNAL_FACTORY_2026-09-03.md SF-1 (a T1 screen and its T2 verdict score the SAME corpus rows) and
SF-2 (K prices only charged T2/T3 trials, so the search width the screen actually had never reaches deflated_p).
S12 (LANDED d55c03da3) built SF-1's fix: `foundry/tiers.py` `partition_corpus` splits SCREEN/VERDICT by iso_week,
`run_tier` raises `ScreenPartitionLeak` on a row off its side, and `screened_n` is required (raises if None,
`charge_path_followups.py:43-44`). SF-2's OTHER half -- "charge the screen: k_global = cumulative_k(prior,
n_screened...), not +1" -- is NOT landed: `backtest_runner.py:192` hard-codes `cumulative_k(prior, 1)` for every
charged call regardless of the printed `screened_n`, so K still undercounts the width the family's screens searched.
PREMISE (step 0): reproduce that SF-1's partition + leak-raise + required screened_n are live in master (run the
existing `foundry/tiers.py` tests); reproduce `backtest_runner.py:192`'s literal `cumulative_k(prior, 1)` and that
no caller threads `screened_n` into it -- grep every call site of `_charge_ledger` for a `screened_n`-derived arg.
LIMIT (step 1): if `_charge_ledger`'s single caller-shared K counter cannot accept a per-call increment without
editing the shared token module `backtest_runner.py` itself, report CLOSED AT LIMIT and name the coupling exactly.
CHANGE (step 2): additive-only helper `scripts/platformkit/foundry/screen_charge.py` (<=300 LOC):
`k_increment(screened_n, charged_at_once=1) -> int` implementing SF-2's rule (increments by the screened count
since the family's last charge, never less than 1); propose the ONE call-site edit inside `backtest_runner.py:192`
(swap the literal `1` for a caller-supplied increment, default 1 so every legacy call is byte-identical) as a
PROPOSED snippet under docs/research/organization-sprint/ -- do not edit backtest_runner.py, tiers.py, ledger.py or
combo/fwer_budget.py this row.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = K_true (screened-charge rule) vs K_currently_charged (+1 rule) on the same synthetic 200-screen,
                  1-charge batch (this row's own CONSTRUCT fixture, not a real family)
  before        = current code: 1 charge -> k_cumulative advances by exactly 1 regardless of screened_n (measured
                  at backtest_runner.py:192)
  bar           = k_increment(200, 1) == 200 (or the printed SF-2 formula's exact value) on the fixture; the
                  proposed one-line diff, applied ONLY inside a scratch copy of backtest_runner.py under test
                  isolation, reproduces the new K on the fixture and the OLD K (+1) on 0 screens (backward compat)
  n             = 3 fixtures (0 screens, 1 screen, 200 screens) (CONSTRUCT)
  eye check     = n/a (S-row); reproduction = verifier re-imports screen_charge.py, reruns the 3 fixtures, diffs K
  must not move = the real backtest_fwer.jsonl ledger (never opened, never charged); every existing threshold
NON-TAUTOLOGY: the 0-screen fixture must NOT silently zero K (a family with 0 screens still charges >= 1 on a real
verdict); this floor is asserted, not assumed.
EVIDENCE: docs/evidence/harness/S234_signal_factory_charge_2026-09-04.md + the fixture JSON. ASCII only.
Calibration language only (no dollar, ROI or edge words).
TEST: one new per-file test (3 CONSTRUCT fixtures), run only that file.
REPORT: SF-1 reproduction result, the K_true vs K_currently_charged table, test line, SHA. Commit by pathspec, no
push. NEVER PARK.
