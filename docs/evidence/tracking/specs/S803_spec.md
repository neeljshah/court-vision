# S803 -- the issue scanner opens one issue per (step, refusal key) the attention table does not name (PAPER ONLY)

## Premise (measured 2026-10-09 16:5xZ, read-only: paper_desk_issues.scan() in-process, no --write, no ledger touched)
- Real 10-08 journal, row `2026-10-08T14:24:27Z schedule timed_out child_timeout refusals {child_timeout: 1}`:
  paper_desk_attention.classification() = attention, but the scan at now 2026-10-08T14:30Z gives `tick_refused schedule PASS`
  (decision `timed_out` is not in {refused, error, failed, degraded}, and the refusal key is never read).
- Real 10-09 journal: `night:2026-10-08 refused step_exception` at 13:27Z reads FAIL at 13:30Z, but PASS at 16:40Z, because the
  16:26Z `night_skipped` row supersedes it. An operator reading issues/<D>.md at 16:40Z never sees the refusal.
- The named S712 case (night_partial / night_skipped carrying `night_artifact_refused`) is written by
  paper_desk_actions.accepted_receipt:138. It is not in the 10-08 / 10-09 journals, so it is a construct.

## Change (owned files only)
- NEW scripts/platformkit/ops/paper_desk_issue_refusals.py `check(ctx)` reads the same two journal days as `_tick`. Per row it takes
  the step's family rules from `paper_desk_attention.ATTENTION_TABLE` (read-only import; the table is unchanged). Each refusal key
  that is neither success nor benign for that family adds to (step, key). A non-dict refusals value or an empty key is counted
  under `refusals_malformed` and skipped (the S642 skip-and-count pattern). Bad and future lines are skipped; `_tick` counts them.
- One `step_refusal_key` observation per (step, key) with subject `<step>/<key>`: FAIL. Severity is P1 for night/capture and P2 otherwise.
  Evidence: the latest row's ts, decision and key=count; the number of rows in the window; and `owner: <row>`
  (night_artifact_refused gives S712, anything else gives unowned). An open subject that is no longer seen gets PASS (closes).
  The ledger counts recurrences.
- paper_desk_issue_checks.check() adds `ctx.guard("refusal_keys", ...)` (+2 lines, 300 LOC).
- Expectation updates: two real-fixture end-to-end tests now also expect `step_refusal_key tick/tick_exception` (the real 09-29 03:15Z
  tick refusal). The directory-named-journal test expects 3 check errors (refusal_keys reads the same path).

## Clauses
- V1 A success-decision row (night_partial) carrying night_artifact_refused gives FAIL `night:<D>/night_artifact_refused` with
  `owner: S712`, while tick_refused for the same step stays PASS (the gap is shown in the same test).
- V2 One issue per (step, key): repeated rows give one observation with the latest evidence and a row count. Benign keys open none.
- V3 Malformed refusals are counted and skipped. The check does not error.
- V4 The issue closes once the key leaves the window, and reopens with recurrences 2 (through ledger.transition).
- V5 The V1-V4 tests FAIL on HEAD's paper_desk_issue_checks.py (no guard registered).
- V6 Real journal re-probe (read-only): at 14:30Z 10-08, `schedule/child_timeout` FAILs. At 16:40Z 10-09, `night:2026-10-08/step_exception` FAILs.
- V7 Every existing test_paper_desk_issue*.py file and the 4 other scanner test files pass, and LOC is <= 300. paper_desk_attention.py is unchanged.
- V8 No $/edge language; PAPER ONLY.

## Fix round 1 (adversarial REJECT on 312ebe19a: M2, M15, M18 survived; real defects 1 and 2)
- A row compacted by paper_desk_limits.bound_row (refusals exactly {journal_row_externalized: 1} plus detail_path) is read
  through its detail file data/cache/paper_desk/<detail_path> (ctx.read, bounded). An unreadable or missing detail keeps
  journal_row_externalized (fail closed). Real 10-03..10-06 externalized night rows: 3 details carry {}, 1 carries child_exited_during_observation.
- A step whose family is unknown to the attention table (classification() = attention) has no benign keys here.
- V9 A refusal key equal to a family success label opens nothing; a capture step is P1; an empty / None / int step is skipped
  without a scan_check_error; an unknown-family step with a tick-benign key opens an issue.
- V10 An externalized row opens the detail file's keys, nothing for {} details, and journal_row_externalized when the detail is missing.
