# S682 cloud result (2026-09-30) -- desk power ledger (report-only)

VERDICTS (verified code = commit 44be71aa on branch cloud/S682-2026-09-30):
- Pre-build critic (independent Opus sub-agent): REVISE, 15 items, all folded as spec AMENDMENT 1.
- Round 1 at d5bd53ca: CONTRACT tier ACCEPT WITH CORRECTIONS; ADVERSARIAL tier ACCEPT WITH CORRECTIONS
  (spec-named ceil->round mutant survived; symlinked data/ bypass; NaN; unvalidated counts; tracebacks). One fix pass = AMENDMENT 2.
- Round 2 (final, re-verify limit reached) at 44be71aa: CONTRACT tier ACCEPT; ADVERSARIAL tier ACCEPT WITH CORRECTIONS
  (no acceptance-rule or B1-B10 / Q1-Q9 violation; corrections listed below are NOT applied on the branch).
- Reviewer independence: codex was not available in the cloud box. The critic and all four verifier passes were
  separate, independent Opus sub-agents spawned for this run; none of them wrote the code. The builder was the orchestrating session.

WHAT WAS BUILT (new files only):
- scripts/platformkit/ops/power_ledger.py (278 lines): declared table of sealed estimands (S503 through the scoreboard
  amendment chain, arm E, S551, S519, M2) plus S643/S644 as NOT_SEALED; floors and secondary floors READ from the sealed
  PREREG files; per estimand n (min over cells), yield per present day over D-6..D, projected floor date or "never"
  (ZERO_YIELD), REACHED / PARTIAL_FLOOR, BEYOND_HORIZON (MLB 2026-11-01), MDE = 2.8 x SE of paired diffs, sha256 of every
  prereg read; CLI writes docs/evidence/forward/power_ledger/<D>.json (refuses data/ and vault/, refuses a differing rewrite).
- scripts/platformkit/ops/power_ledger_input.py (49 lines): accrual validation, refusal by name.
- tests/platformkit/ops/test_power_ledger_s682.py (290 lines): n = 22 (CONSTRUCT), C1-C22. C1 reproduces S557's
  23.6 / 35.8 / 10.0 from its stated inputs. Fails on trunk (module absent).
- Spec: docs/evidence/harness/S682_spec_2026-09-30.md (body + AMENDMENTS 1 and 2).

TEST COMMANDS (one file per process, Ubuntu clone, Python 3.11):
- python3 -m pytest tests/platformkit/ops/test_power_ledger_s682.py -q -> 22 passed
- python3 -m pytest tests/platformkit/test_loc_rail_scope.py -q -> 1 passed
Mutations: all 12 spec A1.11 mutants turn a named case red; the claimed 13
verifier-authored mutations are unverified historical evidence because their
mutation-to-test mapping and outcomes were not archived. One survives
(allow_nan=False, see C-1).

MUST NOT MOVE: no PREREG*.json, seal-pinned file, DESK_STATE.md or register row changed (git diff origin/trunk...HEAD = 5 added files).
Report-only; no estimand, floor or seal edited. Sample-size / calibration language only.

OPEN CORRECTIONS for the landing session (round 2 adversarial; outside the acceptance rule):
- C-1 json.dumps sits outside the CLI try (power_ledger.py ~:262): finite diffs whose sum overflows give mde = inf and a
  traceback (exit 1, nothing written) instead of exit 2. Refuse non-finite mde in mde() and add a C20 case (also kills the allow_nan mutant).
- C-2 OverflowError refusals do not name the estimand.
- C-3 top-level accrual that is not an object (list, null) is treated as no input rather than refused.
- C-4 supersedes.path is not type-checked or confined to --repo-root (int -> TypeError; ../ reads outside the root, read-only).
- C-5 stale test docstring ("19 cases, AMENDMENT 1"; now 22, AMENDMENT 2).
NEW GAP lines (from round 1): guard protects only --repo-root's tree; C11's seal-pinned hash check is effective on the
real repo only; PARTIAL_WINDOW and absent secondaries are reported, not escalated; the seal-pinned list has no canonical
machine-readable source; one unparseable scoreboard PREREG aborts the whole ledger rather than flagging S503.

NOT VERIFIED:
- Real accrual counts (n, daily yield, cells, paired diffs) for every estimand: the clone has no data/ and the nights live on
  the laptop. No real <D>.json ledger was written or committed; every real projection is NOT VERIFIED.
- The S676 digest (night yield) that should feed --accrual does not exist yet; wiring into the tick is not in scope.
- docs/evidence/harness/GAP_REVIEW_cloud_2026-09-30.md, cited by the slate row, is not on trunk; it was not read.
- Python 3.10 (laptop) run.

PORTABLE: yes (code and construct tests); the real morning run needs laptop accrual input.
