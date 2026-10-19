# S500 paper desk tick

FIX r8 is implemented with construct fixtures only. Machine: Windows,
C:/Users/neelj/nba-harness-h144. Binding sources: S500_spec.md AMENDMENTS 6a,
6b, 7, and 8, plus _verdict_s500_r8.md. No archive, network, pod, real process,
task installation, or scored measurement was used. Pinned starting revision:
e1466de68b70c9049f2697f95813fc81ed148bc6.

## FIX r1

Historical summary: OS lock, bounded subprocess ownership, exact D1 clocks,
schedule evidence, census/capture checks, atomic status, and the unattended task.

## FIX r2

Historical findings: conservative process identity, OS-lock-only admission,
durable append/recovery, and start-only capture recovery are retained.

## FIX r3

Historical findings: launch failures reconcile, producer census counts validate,
same-clock sequence orders, failed nights back off, and budget/owner checks hold.

## FIX r4

Historical findings: census validates producer counts; night failures back off;
subject attention persists; uncertain owners block; corrupt state fails closed.

## FIX r5

Historical findings: capture, schedule, night, and census attention surface;
sharing violations retry atomically; refused outcomes remain visible.

## FIX r6

Historical findings: classifier defaults unknown strings to attention; clear paths
and replay hold; journal failure count/names persist; tail repair uses atomic retry.

## FIX r6b

Historical findings: exceptional lock recovery is attention; clean tick/replay
clear paths hold; genuine WinError fixtures cover terminal counters and tail repair.

## FIX r7

Historical findings: malformed classifier inputs fail closed; strict clear and replay paths hold; dated subjects, per-family expiry, repair, and aliases are covered.

## FIX r8

All reproductions are construct fixtures under the system temporary directory.
No committed JSON fixture or seal was added; JSON EOL rules remain
`docs/operations/paper_desk_config.json text eol=lf` and
`docs/evidence/forward/desk_audits/*.json text eol=lf`.

- 8(a), verifier BLOCKING: "malformed outcome fields (decision, reason, reconciliation status, refusal keys: missing, non-str, empty, NaN, Inf, -Inf, numbers, bools, containers) are validated and converted to a serializable attention sentinel BEFORE any sort, dedupe or serialization in latest_families, recover_status and journal; no ValueError/TypeError escapes from these paths for such rows. End-to-end regression through latest_families AND through journal + recover_status replay for decision=NaN, reason=Inf, reconciliation.status=-Inf, refusal key NaN, and a missing decision: each yields the family's attention key, never an exception." Before: `decision: ValueError: Out of range float values are not JSON compliant`; the same verifier probe reported ValueError for reason Inf, reconciliation status -Inf, and refusal-key NaN. After: r8 sends all five named values through latest_families, journal, and recover_status; each produces tick_attention, 9 passed. `normalize_outcome` supplies malformed_outcome before ordering or JSON.
- 8(b), verifier BLOCKING: "every day-family step (schedule, night, census) and both aliases (nights, census_scan) are seeded with the tick's UTC-date subject before anything that can raise; a subject is overwritten only by a string that passes date.fromisoformat and is exactly YYYY-MM-DD. Regressions: a night:abcdefghij step keeps the tick-date subject; census_scan raising early (invalid backfill_days) carries the tick-date subject; both expire normally." Before: `night_subject abcdefghij` and the verifier's early census_scan probe reported `subject=None`. After: `night_subject 2026-09-29`, `census_subject 2026-09-29`; r8 expires both under their own windows.
- 8(c), verifier BLOCKING: "every attention_expired entry carries its family; dedupe by (family, subject, decision); an existing entry without family is read compatibly (treated as its own family unknown, never merged into another family's entry). Regression: schedule and night entries with the same subject and decision stay two entries, live and after replay." Before: one expired `{'subject': '2026-09-20', 'decision': 'refused', ...}` represented both schedule and night. After: r8 finds two entries with families schedule and night, live and replay, and retains a family-less legacy entry as unknown; r6 attention/replay shape expectations add the required family field.
- 8(d), verifier BLOCKING: "a step whose family is not in the table is ALWAYS attention (grouped under tick), whatever its decision, reason or refusals. Regression: {step: unknown_step, decision: tick_ok, reason: complete, refusals: {}} is attention." Before: unknown_step/tick_ok returned no tick_attention. After: `unknown_tick_attention True`; r8 forces unmapped raw families to attention before tick rules can accept tick_ok.
- 8(e), verifier correction: "regression: a heartbeat ran row with exit_code None does not clear heartbeat_attention (live and replay)." Before: no construct regression covered the None case, although the implementation was confirmed correct. After: r8 journals degraded then ran/None and confirms heartbeat_attention live and after recover_status replay.

## FIX r9 (orchestrator-direct, AMENDMENT 9)

- 9(a): attention_expired entries are rewritten with family (legacy -> "unknown"),
  deduped newest-ts per (family, subject, decision) independent of input order, and
  sorted by (ts, family, subject) (paper_desk_attention.py latest_with_attention).
  Before: a legacy entry was kept without family and reversing two duplicates changed
  the retained ts (sol r8 probe). After: test_paper_desk_r9_attention.py legacy,
  order and sort regressions pass.
- 9(b): adjudicated non-blocking; verifier-created root tmp*/ trees share the scratch
  exemption of .s500_tmp/ and .s500_verify/, are never staged, never deleted.
- 9(c): the per-file count below matches the table (31 files including r9).
- 9(d): end-to-end regressions for the nights alias and a schedule raising before D1
  (bad local_tz) with journal replay and expiry, the legacy-family collision through
  journal(), and an unknown-family row replayed from the journal.
- 9(e): the status reader drops and counts (invalid_status_record) any expired entry
  whose subject, decision, ts or present family is not a str; journal() no longer
  raises on ts=5, subject=[1], decision={"a":1} or family=[1] (it raised TypeError).
- 9(f): unknown-family recovery documented under Owner recovery.

Owner clear paths: capture requires same-name capture_present; schedule, night,
and census require same-day success or their own expiry; heartbeat requires ran
with integer exit zero; tick requires later empty-refusal tick_ok from a lock-owning
non-dry tick; lock requires lock_acquired. Expiry keeps family, subject, decision,
and ts for review and prunes entries older than 14 days.

## Owner recovery (AMENDMENT 3(e), 4b(e); restored by the orchestrator after the r8 collapse)

All paths are under data/cache/paper_desk/ in the main checkout.
- capture_owner_intervention_required for <name>: first confirm no capture_supervisor,
  hidden_launch wrapper or writer for <name> is running (Task Manager or a psutil scan
  of command lines). Then inspect and remove capture_request_<name>.json and
  launch_<name>.json (paper_desk_tick.py:145-146). The next tick retries the start-only
  launch; capture_attention clears on the first capture_present for <name>.
- A pending inflight_producer.json or inflight_launch_<tag>.json that stays blocked:
  confirm the recorded owner pids are gone, then remove the marker; the next tick runs.
- night_failure_state_unreadable (a corrupt night_failure_state.json) defers every
  night with a counted refusal: inspect it, delete it, and the next tick retries
  (paper_desk_actions.py:26-45).
- attention_expired entries need no action; they record what aged out of the scan
  window and are pruned after 14 days.
- An unknown-family row (a step the table does not know, e.g. from a hand-edited or
  future-version journal line) is always tick attention and never expires: archive
  the offending journal line or file, delete status.json, and the next tick replays.

## Reproduction and final results

Run each file separately: `python -m pytest <file> -q -p no:cacheprovider`.
Every input is construct-only and no test reads a moving git reference. Final
run: 416 passed across 31 per-file invocations (31 table rows below).

| File | Passed |
|---|---:|
| test_paper_desk_tick.py | 14 |
| test_paper_desk_steps.py | 25 |
| test_paper_desk_runtime.py | 14 |
| test_paper_desk_integration.py | 4 |
| test_paper_desk_amendment.py | 14 |
| test_paper_desk_evidence.py | 20 |
| test_paper_desk_limits.py | 2 |
| test_paper_desk_start.py | 34 |
| test_paper_desk_process.py | 24 |
| test_paper_desk_job.py | 4 |
| test_paper_desk_task.py | 10 |
| test_paper_desk_r2_evidence.py | 27 |
| test_paper_desk_r2_runtime.py | 8 |
| test_paper_desk_r2_steps.py | 11 |
| test_paper_desk_r3_evidence.py | 1 |
| test_paper_desk_r3_limits.py | 2 |
| test_paper_desk_r3_process.py | 2 |
| test_paper_desk_r3_runtime.py | 9 |
| test_paper_desk_r4_attention.py | 29 |
| test_paper_desk_r4_evidence.py | 20 |
| test_paper_desk_r4_process.py | 5 |
| test_paper_desk_r4_runtime.py | 7 |
| test_paper_desk_r5_atomic.py | 3 |
| test_paper_desk_r5_attention.py | 2 |
| test_paper_desk_r6_atomic.py | 2 |
| test_paper_desk_r6_attention.py | 39 |
| test_paper_desk_r6_replay.py | 3 |
| test_paper_desk_r7_attention.py | 42 |
| test_paper_desk_r8_attention.py | 9 |
| test_paper_desk_r9_attention.py | 10 |
| test_paper_desk_reconcile.py | 20 |

n = 416 (CONSTRUCT); no sampled or scored comparison. All landing files are
ASCII and <= 300 lines. Preflight uses `--base master` only as a command-line
gate argument; no test/memo check compares a moving ref. Verdict/scratch paths
are excluded. Tick/start --help and installer Get-Help are final checks.

SHA: NOT CREATED (sandbox); files ready for lane_commit

## NOT VERIFIED

- Real WMI starts, Windows Job containment, deployed inventory, capture
  coexistence, real memory use, and zero visible descendant consoles.
- Production dry/live ticks, task registration, scheduled ticks, logoff/sleep
  recovery, power loss, real corpus execution, and on-time equivalence.
