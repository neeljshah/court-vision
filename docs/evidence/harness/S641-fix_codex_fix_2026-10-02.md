# S641 fix review remediation - 2026-10-02

## Finding one

CONFIRMED. `scripts/platformkit/mcp_server/served_asof.py:105` read only the
schema before returning an undated input at the next line. An undated tennis
fixture with a successful schema read and a synthetic `read_table` error reached
the mtime result on the unfixed implementation, so the finding is reachable.

Fix: `_max_played_date` now calls `pq.read_table(path)` before it accepts an
undated parquet. The existing exception boundary maps a failed data-page read to
`input_unreadable`, with an unknown as-of.

Construct: `test_undated_table_read_error_is_unreadable` in
`tests/platformkit/mcp_server/test_served_asof_s641_fix.py`. With the one-line
fix temporarily removed, its one-test replay failed at
`assert env["as_of"] is None`: the result had `as_of_source` `input_mtime`.
The fix was restored before the recorded test runs.

## Test runs

- `test_served_asof_s641_fix.py`: twelve passed.
- `test_served_asof_s504.py`: twenty passed.
- `test_envelope_contract.py`: six passed, one failed with `-x` at A06:
  `ask` returned `status='no_data'` without the required note. This is outside
  the changed as-of path and is not a Windows path, CRLF, separator, or file-lock
  condition; no production or fixture change was made for it.

Windows-only failures: none observed. The new construct and both passing files
used Windows temporary paths successfully.

Preflight passed for all four touched files with the S641 spec: vocabulary,
index-side CRLF handling, line limits, schema, artifact, and row checks passed.

## NOT VERIFIED

- The complete envelope-contract file is not green because of the unrelated A06
  no-data response noted above.
- No live or non-synthetic parquet was opened; this is paper-only validation.
- Landing remains subject to the review-required re-verification.

## FIX ROUND 2 (2026-10-02)

- CONFIRMED MEDIUM: `scripts/platformkit/mcp_server/served_asof.py:151`
  reused a prior parquet read when metadata was unchanged. A later read error
  was skipped and the old date was served. The serving path now calls
  `_max_played_date` on every request. The dated and undated cases in
  `test_second_call_rechecks_readability` both return `input_unreadable` and
  unknown as-of. `test_warm_call_then_exclusive_windows_lock_is_unreadable`
  also covers both cases with a real Windows CreateFileW lock. With the old
  cache block temporarily restored, each lock case
  failed at `assert env["as_of"] is None` (the test helper assertion); the fix was restored.
- CONFIRMED LOW test-power gap: the original fixture cleared `_CACHE` on each
  test, so it did not exercise a repeated call. Serving no longer consults
  `_CACHE`; the attribute remains only for S504 test compatibility. The new
  `test_second_call_sees_rewrite_with_unchanged_metadata` changes a parquet
  date while preserving file size and mtime. With the old cache block restored,
  it failed at `assert second["as_of"] == "2026-09-29"` (test line 178).
- The verifier's envelope failures are reproduced and remain red. A06 returns
  `no_data` without a note from
  `scripts/platformkit/answers/schedule_context_resolver.py:195-197` when the
  MLB calendar is absent. The test is correct; the production return needs a
  note. X06 returns `ok` for
  `scripts/platformkit/analytics_showcase/out/paper_execution_audit.json` with
  `as_of=2026-07-25T11:13:31.118202+00:00`, about 69 days old against its
  two-day bound. The test is correct; the serving handler needs to enforce the
  bound. Both production fixes require paths outside this row's explicit edit
  list. No fixture was changed to hide either failure, and no data was written.
- Per-file results: `test_served_asof_s641_fix.py` had seventeen passed;
  `test_served_asof_s504.py` had twenty passed;
  `test_envelope_contract.py` had forty-nine passed and two failed (A06, X06).
  The five new S641 cases each failed against the temporarily restored cache
  block and passed after restoring the fix.

NOT VERIFIED: live corpora, deployed services, sustained concurrent writers,
or live capture. The envelope contract remains red on the two baseline cases.
