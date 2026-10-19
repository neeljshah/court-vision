# S663 cloud result -- 2026-09-30 (desk-improve routine, one-off override, Opus, Ubuntu cloud clone)

Row: S663 (per-feed per-game latency ledger), PINNED by the one-off override in
docs/evidence/harness/QUANT_GRADE_BUILD_SLATE_2026-09-30.md section 3a; row text from section 2.
Branch `cloud/S663-2026-09-30` from trunk e1b3bcdc (commits 5625e8e8 build, 5d2ad8e1 + 6e4eb0b6 fix
round 1). Spec: docs/evidence/harness/S663_spec_2026-09-30.md (27-line body + AMENDMENT 1 critic +
AMENDMENT 2 fix round). The register and DESK_STATE.md are NOT edited on this branch (override rule).
Latency measurement language only: not a forecast and not a trading claim.

Codex is not available in this box. The pre-build critique and every verifier tier were
INDEPENDENT OPUS SUB-AGENTS (separate contexts that did not build the code); the adversarial tiers
ran in isolated git worktrees.

## Verdicts

| Tier | Round | Verdict |
|---|---|---|
| Pre-build critique (astra) | - | REVISE: 4 BLOCKING + 7 MINOR, all folded as AMENDMENT 1 |
| CONTRACT (A, B1-B10, Q1-Q8 + spec) | 1 (5625e8e8) | ACCEPT WITH CORRECTIONS (1 correction: L3 key names/precision -> A2.1) |
| ADVERSARIAL (mutants + probes) | 1 (5625e8e8) | REJECT: code behaved correctly under probes, but 4 of 12 required mutants and 11 own mutants survived (test coverage) |
| CONTRACT | re-verify (6e4eb0b6) | ACCEPT |
| ADVERSARIAL | re-verify (6e4eb0b6) | ACCEPT (all previously named mutants red; 14 new mutants red; 5 own mutants survive = equivalent or unbound, filed as NEW GAP below) |

Fix round 1 (the single allowed round): the new test file test_latency_ledger_mid.py (F1-F9 plus
exact 10 s prior-age and horizon-tail cases), plus three code corrections (AMENDMENT 2 A2.2):
a NO_RECEIPT_CLOCK mid-block reason, one global RSS state-line counter across sports, and a missing
--state-root is refused with exit 2. No bar or constant moved: FLAG_P95_S 60.0, OFFSET_BOUND_MS 250,
MID_HORIZON_S 300, MAX_WAIT_S 10, MIN_N_FLAG 30.

## What was built (new files only)

- scripts/platformkit/ops/latency_ledger.py (207 lines, pure core). S592 events are reproduced
  exactly (E5/E6/E7 + its AMENDMENT 1). The per (sport, feed, game) blocks are receipt_minus_event,
  receipt_minus_source and first_mid_change_minus_event, each with p10/p50/p90/p95/p99 on 0.5 s bins.
  The core also computes poll_wait_ub (an upper bound), book_moved_first, change_after_next_event,
  the p95 flag and the pooled rows. A missing stamp prints NO_SOURCE_CLOCK, never 0.
- scripts/platformkit/ops/latency_ledger_io.py (221 lines). State shards are streamed through the
  S592 bounded reader. Books and schedules go through the S550 loaders (read-only reuse). The module
  also reads the optional S664 offset journal, runs the CLI and writes the output atomically. Exits:
  0 ok, 2 refused (open shard unless last <= today-2), 5 RSS cap.
- Tests: tests/platformkit/ops/test_latency_ledger.py, test_latency_ledger_io.py,
  test_latency_ledger_mid.py; helper s663_shards.py. The tests use synthetic shards in tmp_path
  only, with no network and no data/ read.
- Unchanged, byte-identical: ingame/state_source_latency.py and execution/exec_quality_audit_io.py.
  No seal-pinned file was touched, including local_capture_writer.py and capture_watchdog.py.

## Tests (one file per process, branch 6e4eb0b6)

| Command | Result |
|---|---|
| python3 -m pytest tests/platformkit/ops/test_latency_ledger.py -q | 8 passed |
| python3 -m pytest tests/platformkit/ops/test_latency_ledger_io.py -q | 5 passed |
| python3 -m pytest tests/platformkit/ops/test_latency_ledger_mid.py -q | 8 passed |
| python3 -m pytest tests/platformkit/test_loc_rail_scope.py -q | 1 passed |
| python3 -m pytest tests/platformkit/ingame/test_state_source_latency.py -q | 32 passed (unchanged import) |
| python3 -m pytest tests/platformkit/execution/test_s550_exec_quality_audit.py -q | 36 passed (unchanged import) |
| python3 -m pytest tests/platformkit/test_s140_loc_rail.py -q | 1 failed / 2 passed: PRE-EXISTING. It fails identically on trunk e1b3bcdc (ModuleNotFoundError statsmodels), not S663 |

The acceptance rule is n = 22 (CONSTRUCT): C1-C12, C7b and F1-F9. Committed C7/C7b constructs
check pooled receipt_minus_event against S592 play_lag and receipt_minus_source against S592
fetch on the same shards; C7 uses seed 663, mlb/nfl and two days.
Historical fuzz (8 seeds x mlb/nfl/nba_pbp x 2 days, 0 mismatches of 24): NOT VERIFIED;
no committed reproducer or result artifact supports that historical claim.
The code on trunk has no ledger module, so every new test fails there.

## NOT VERIFIED (the clone has no data/ directory; venue and sports hosts are blocked)

- The real run on 2026-09-22..09-30 MLB, and the S592 play-lag p50 22.0 s reproduction within
  0.5 s. Both need the archive; run on the recorder box after 2026-10-02 so the book shard d+1 is
  closed.
- The offset column. It needs S664 adoption, and until then every game prints OFFSET_UNMEASURED.
  The journal schema {ts_utc, offset_ms} is provisional until S664 is built.
- Real mid-join coverage and censoring rate. Focus snapshots exist only in the focus hour (S556),
  so heavy censoring is expected.
- Real-archive peak RSS under 400 MiB.
- Any Windows behaviour.

## NEW GAP lines (from the verifier tiers; not rejections)

- NEW GAP: an event just after 00:00Z whose only prior snapshot is in the day d-1 book reads
  no_prior_book. Books d and d+1 are loaded per state file; load d-1 as well, or name the reason.
- NEW GAP: book-shard identities and book counters are counted twice across overlapping d/d+1 loads
  in `inputs` and `counters`.
- NEW GAP: a pooled row that mixes served and unserved games can label its mid block
  NO_BOOK_SNAPSHOTS / ALL_NO_PRIOR_OR_CENSORED instead of NO_RECEIPT_CLOCK. This is cosmetic; the
  counts are correct.
- NEW GAP: the spec body's ACCEPTANCE block still reads n = 12. The binding values are A1.12 (13)
  and A2.3 (22).
- NEW GAP: four untested details:
  - the inclusive journal window end (a row exactly at max RE);
  - the even-n median of offset_ms;
  - lag == 0 counts lag_nonpositive but not lag_negative;
  - the poll_wait upper clip at lag, which is reachable only when RQ > RE, so it needs a ruling on
    whether such rows are in scope.

PORTABLE: yes (code and construct tests run on Ubuntu). The real-archive run is WINDOWS, on the
recorder box.
