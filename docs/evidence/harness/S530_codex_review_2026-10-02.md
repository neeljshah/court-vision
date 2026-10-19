### S530 - LAND AFTER FIX

The report uses authoritative game-key attribution with ticker/state corroboration (`scripts/platformkit/execution/soccer_cohort_report.py:103-110`) and refuses conflicted keys from every league cohort (`soccer_cohort_report.py:119-177`). No partial-row merge or cross-night look-ahead defect found.

Windows blocker: the output writer uses bare `os.replace()` (`soccer_cohort_report.py:256-261`).

Exact fix, under 10 lines:

- Import `replace_with_retry` from `scripts.platformkit.ops.atomic_replace`.
- Replace `os.replace(tmp, path)` at line 259 with `replace_with_retry(tmp, path)`.
- Change the failure injection at `tests/platformkit/execution/test_soccer_cohort_report.py:221` to monkeypatch `m.replace_with_retry`.

The existing atomic-failure test then continues to prove that the prior artifact survives (`test_soccer_cohort_report.py:215-223`).

Must land after: S490, which is already on `master`.

| private/cloud/S530-2026-10-02 | LAND AFTER FIX | S490 already landed | bare `os.replace` | S |

1. Fix and land S530.
