GAP S156 | sport all | worktree a16 | log cx_s156_absent_evidence_escapes
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it; self-check
against every line of section B before you report. S-row: eye check = n/a.
PREMISE (step 0, re-measured 2026-09-04, main repo): three unrouted absent-evidence escapes, same
B3 shape as S153/S154, none FALSIFIED. (1) test_ledger_schema_s13.py:106-107 (in
test_next_k_family_counts_aliased_rows_s89) `if not path.exists(): return` -- private, skips the
file's own _require_real_ledger (:22-28) though worktree_marker is imported (:15). (2)
test_calibration_report.py:175-176 (in test_the_default_report_still_reproduces_...) `if not
landed_path.exists() or not (.../"combo").exists(): pytest.skip(...)` -- no worktree_marker
import in the file. (3) test_tick_informative.py:65-66 (in
test_requote_reproduces_the_published_ci) `if not (_CACHE/spec["csv"]).exists() or not
(_CACHE/spec["json"]).exists(): pytest.skip(...)` -- same, no import. BEFORE, evidence present,
main repo (`python -m pytest <file> -q -p no:cacheprovider`): 8/8, 9/9, 17/17 passed, 0 skipped.
LIMIT (step 1): n/a (CONSTRUCT).
CHANGE (step 2): route each of the 3 spots through worktree_marker -- skip when
is_worktree_checkout(), else pytest.fail naming the absent path -- mirroring
_require_real_ledger (:22-28) and test_family_bars.py:32-39. (1) call the file's own
_require_real_ledger(path) instead of the private return. (2)/(3) add `from
scripts.platformkit.eval_gate import worktree_marker` and replace the bare skip guard. No new
shared helper unless unavoidable (<=300 LOC, scripts/platformkit/eval_gate/). Nothing else moves.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = absent-evidence escapes routed through worktree_marker, over the 3 enumerated
  before        = 0/3
  bar           = 3/3
  n             = 3 (CONSTRUCT)
  eye check     = n/a (S-row); reproduction = verifier runs all three files in the MAIN repo
                  (count-before == count-after: 8/8, 9/9, 17/17, 0 new skips) and monkeypatches
                  one absent path per file (FOUNDRY_WORKTREE=1 -> skip; unset in main repo -> fail)
  must not move = every module under scripts/platformkit (tests + memo only); backtest_fwer.jsonl
                  byte-identical, 18 rows
NON-TAUTOLOGY: metric covers exactly the 3 enumerated escapes, no row excluded. In the worktree
the caches/ledger are absent (never junctioned) so the lane's own runs SKIP there -- expected, not
fix evidence; the main-repo counts are what must hold.
EVIDENCE: docs/evidence/harness/S156_absent_evidence_escapes_2026-09-04.md -- before/after table
per file, the three pytest outputs verbatim (main repo), the two monkeypatch outcomes per file,
NOT VERIFIED list. Calibration language only.
TEST: the 3 pre-existing files via `python -m pytest <file> -q -p no:cacheprovider`, plus one new
test per file from CHANGE.
COMMIT: explicit pathspec (3 test files + memo, + shared helper only if added), in the worktree,
no push, report the sha. NEVER PARK: finish with the report and SHA line.
