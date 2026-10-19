# S709 cloud result 2026-09-30 -- DESK_ROOT resolver for the paper-desk config

PAPER ONLY. Calibration and operations language only. Nothing here places, routes or simulates an order.
Run: cloud routine desk-improve with a one-off override (row PINNED to S709, from
AUTOMATED_PAPER_DESK_ARCHITECTURE_2026-09-30.md section 3a). Machine: Claude cloud Ubuntu clone, Python 3.11,
no data/, no venue or sports host contacted. Branch cloud/S709-2026-09-30 (not trunk, not landed).
Reviewers: codex is not available here. The pre-build critic and each verifier tier were INDEPENDENT Opus
sub-agents, none of which built the change: critic, CONTRACT tier, ADVERSARIAL tier, and one combined
re-verification pass after corrections.

## Verdicts

| Stage | Verdict | Notes |
|---|---|---|
| Pre-build critic | REVISE (15 items) | all folded as spec AMENDMENT 1; premise corrected (TWO consumers of captures.*: tick.py:144/260 in-process + paper_desk_start main) |
| CONTRACT tier (on 975539f6) | ACCEPT WITH CORRECTIONS | premise 44/29/15/0 reproduced; A2 headline reproduced by own script; corrections: P3 import line + behaviour notes; this memo was missing (A7) |
| ADVERSARIAL tier (on 975539f6) | ACCEPT WITH CORRECTIONS | 25/26 mutants RED; M21 (CLI byte_identical hard-coded) survived; probes found fail-open on non-separator boundaries (quote, ";", NUL, space), weak root validation ("." segments, NUL), AttributeError for a non-string env |
| Re-verification (on fe186bf4) | ACCEPT WITH CORRECTIONS | 6/6 targeted mutants RED; one extra mutant M7 (space as path char) survived -> fixture added, M7 now RED (checked on a copy: 1 failed, 30 passed) |

Final: ACCEPT WITH CORRECTIONS. Every correction is applied on the branch. This is the one allowed fix plus
re-verify cycle; there was no REJECT.

## What was built (additive, new files only)

- scripts/platformkit/ops/desk_root.py (164 lines). It provides desk_root, rebase, resolve_config,
  roots_agree, census and a CLI. With DESK_ROOT unset, empty, or naming the default (any case, either
  separator, trailing separators ignored), it returns an unchanged deep copy. Any other absolute root
  rebases every string that starts with C:\Users\neelj\nba-ai-system at a path boundary. It fails closed
  (ValueError) on a leftover default-root path or an invalid root.
- tests/platformkit/ops/test_s709_desk_root.py (204 lines, 31 cases, CONSTRUCT). It fails on old code:
  on trunk bb34a09c the import raises ImportError (checked by the adversarial tier).
- docs/evidence/harness/S709_spec_2026-09-30.md (spec + AMENDMENT 1).
- docs/evidence/harness/S709_PROPOSED_desk_root_diffs_2026-09-30.md: PROPOSED only, NOT applied.
  P1 tick main (resolve + roots_agree fail-closed), P2 start main, P3 fault-matrix LIVE_ROOT (with a
  protection-guard warning), P4 task installer `--env DESK_ROOT=$Root`. P1 and P2 must land together.

## Acceptance (spec bar, reproduced)

- Premise: committed config sha256 ea52bf3c...cde49cd217. 44 profile strings: 29 under the root, 15
  outside, 0 embedded.
- DESK_ROOT unset / empty / default: the json.dumps bytes (sort_keys and indent=2) equal the committed
  config's. All 29 resolved paths equal the committed paths. On Linux the 15 contract cases are identical
  (capture_cwd_not_absolute x15, today's Linux outcome). CLI byte_identical=true.
- DESK_ROOT = scratch dir: capture_config accepts 3/3. inspect_capture gives absent/no_capture_process 3/3
  and deferred/stop_present 9/9 (each stop_path created one at a time under tmp_path). 29/29 strings are
  rebased, 0 default-root strings are left, and the 15 outside strings are byte-equal.
- Windows target roots (D:\desk, D:/desk, D:\desk\\, UNC): these are string-level checks only. 29 strings
  are rebased in the root's separator style and every cwd passes ntpath.isabs.
- Must not move: `git diff --name-status trunk..HEAD` shows only the S709 files (status A). The config,
  the paper_desk_*.py files, capture_supervisor*.py, the register and DESK_STATE.md are unchanged. No
  seal-pinned file is touched.

## Test commands (per file, this clone)

- `python3 tools/desk_bin/run_files.py . tests/platformkit/ops/test_s709_desk_root.py` -> 31 passed
- `python3 -m pytest tests/platformkit/ops/test_s709_desk_root.py -q` -> 31 passed
- `python3 tools/desk_bin/run_files.py . tests/platformkit/test_loc_rail_scope.py` -> 1 passed
- `python3 tools/desk_bin/run_files.py . tests/platformkit/ops/test_paper_desk_start.py` -> 34 passed (untouched consumer)
- `python3 -m scripts.platformkit.ops.desk_root` -> census 44/29/0/15, byte_identical true

## NOT VERIFIED

- The Windows tick contract run on the laptop or recorder, with and without DESK_ROOT. The row names this
  as NOT VERIFIED.
- Adoption of the PROPOSED diffs P1-P4: they are not applied, so today's tick and launcher never read
  DESK_ROOT.
- Real process tables, WMI launches and STOP files on Windows. The Windows roots are checked at string
  level only.
- Nothing under data/ (absent from the clone).

## NEW GAP candidates (for the register owner; no id invented here)

- The 15 profile strings outside the repo root (python.exe / pythonw.exe, bin\hidden_launch.py,
  winroots.pem) have no variable. A VM with another user name or Python path needs its own resolver or a
  per-box config.
- Dict keys are neither rebased nor checked by the leftover guard. Today's config has no path keys.
- Default-root spellings with doubled separators or "." segments inside (C:\Users\\neelj\...) are not
  normalised: they are treated as a new root and the config is rewritten. Today's installer passes
  Resolve-Path output, which is already normal.
- A config VALUE under the root containing ".." rebases verbatim (/desk/../../etc). The tick's local()
  containment check covers relative paths only.
- A DESK_ROOT nested under the default root (C:\Users\neelj\nba-ai-system\sub) is always refused
  (fail-closed, but it blocks that layout).
- UNC roots without a share (\\srv) are accepted.

PORTABLE: yes (resolver + test run on Ubuntu; adoption and the tick contract run are WINDOWS).
