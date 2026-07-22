# Unattended Systems That Fail Visibly -- the reliability stack behind an overnight agentic build

> This platform is built to run unattended for days at a time under an agent fleet. The
> engineering that makes that safe is not the absence of failures -- it is the machinery that
> makes a failure *loud*. The single truth-source for any figure below is
> [docs/JOB_EVIDENCE_PACKET.md](../JOB_EVIDENCE_PACKET.md) (sections B and G).

---

## The claim

A system that runs overnight with no human watching has exactly one unacceptable failure mode:
failing *silently*. A wedged loop, a full disk, a dropped alert, a corrupted ledger, or a
dashboard that stays green over a dead subsystem are all worse than a crash, because a crash at
least announces itself. So the reliability work on this platform is organized around a single
principle -- an unattended run must fail LOUDLY -- and the sharpest proof of that principle is a
health readout that was caught rolling up green over a genuinely-down subsystem, fixed, and now
reports `OVERALL: RED` with the specific broken subsystem named. On this page a red status,
honestly reported, is a feature receipt, not an embarrassment. That is the whole point of the
stack: it is the difference between "looked fine" and "is fine."

---

## The reliability stack

**A watchdog-supervised daemon fleet.** Nine real long-running daemons (in-play projection,
settlement, CLV tracking, risk/bankroll monitoring, line scanning, lineup ingest, and a
dashboard, all paper-only) each carry genuine loop and scheduler logic, and sit under a watchdog
plus registry supervisor. When a process dies, the watchdog relaunches it from the registry
rather than leaving a silent hole in the fleet. Paths: `scripts/daemon_watchdog.py`,
`scripts/daemon_registry.json`.

**An alerting subsystem that survives its own failure modes.** The alert layer
(`scripts/execute_loop/L22_alerting.py`, 669 LOC) is hardened against the ways alerting itself
breaks: a token-bucket rate limiter so an error storm cannot self-DOS the channel; an
atomic-write dead-letter queue so an alert that fails to send is retried, not dropped; and a
per-channel circuit breaker so one wedged webhook does not block the others. EventBus-integrated;
15 tests pass. An alerting layer you cannot trust under load is worse than none.

**A transactional ledger built for concurrent writers.** The paper P&L ledger
(`src/betting/pnl_ledger.py`, 562 LOC) records positions in *units* -- place, settle, void --
behind cross-platform file locking with stale-lock recovery and atomic writes, so two processes
writing the same ledger cannot corrupt it or lose a row. This is the durability engineering, not
a result: no dollar figures, no edge claim. The locking is proven rather than asserted -- a
check-then-append TOCTOU race was later caught and closed with a shared lock, verified by a real
two-OS-subprocess race test (`scripts/platformkit/test_clv_ledger_io.py`).

**Failsafe sentinels that watch the watchers.** The sentinel layer
(`scripts/platformkit/ops_sentinel/`) is the set of tripwires that make an overnight run fail
visibly: disk-pressure (`disk_space.py`), exception-burst (`exception_burst.py`),
stalled-heartbeat coverage (`heartbeat_coverage.py`), a wedge-restarter (`wedge_restarter.py`),
and hash-based tamper-evidence on the invariant-enforcing code itself (`guard_integrity.py`).
Each sentinel ships with its own test file.

**A serving layer wired to fail safe.** The FastAPI surface -- roughly 99 endpoints across 12
routers, counted by booting `api.main:app` and enumerating routes at runtime rather than scanning
decorators -- includes the operational guardrails an automated system needs: a drawdown-triggered
kill switch (`/api/risk/status`) and an ops/health dashboard (`/health/ops`) that aggregates
scraper lag, feed freshness, and drift flags. Path: `api/main.py`.

---

## The RED-report story

The stack above is only worth as much as your ability to know when it breaks, so the capstone is
a one-command liveness harness: `scripts/platformkit/proof_harness/system_proof.py` composes the
gates, sentinels, and ledgers into a single health readout. It had a real bug -- a down section
could still roll up to an overall green. Commit `2eedc37e` ("stop decorative GREEN on
drift/staleness/empty-registry") is the fix, and the receipt that the fix works is not a green
checkmark -- it is a red one. A live run on this box this session returned `OVERALL: RED` and
named exactly what was wrong: 1 of 45 heartbeats RED (`m41_public_splits`), 8 census-drift entries
plus 1 missing store, and 6 autonomy jobs in PENDING-RESTART. A health readout that cannot turn
red is decoration; one that names its own failing subsystems is the reliability feature.

The fleet behind it is verified to actually come back, too. The autonomy layer has been restarted
twice under a sanctioned procedure -- read the stop flag, kill only the live supervisor PID, let
the watchdog relaunch, verify readiness -- landing `all_ready` 44/44 processes, with the runtime
job-report showing every scheduled maintenance and execution category dispatched and honest
watermark/cadence skips recorded as skips rather than dressed up as runs.

---

## Receipts

| Reliability component | Failure it makes visible | Committed path |
|---|---|---|
| Watchdog-supervised 9-daemon fleet | Dead daemon left as a silent hole | `scripts/daemon_watchdog.py`, `scripts/daemon_registry.json` |
| Alerting: token-bucket + dead-letter + circuit breaker | Alert self-DOS / dropped alert / one wedged webhook blocking others | `scripts/execute_loop/L22_alerting.py` |
| Transactional units ledger (locking, stale-lock recovery, atomic writes) | Concurrent-writer corruption, lost row, TOCTOU race | `src/betting/pnl_ledger.py`; race test `scripts/platformkit/test_clv_ledger_io.py` |
| Ops sentinels (disk / exception-burst / heartbeat / tamper-evidence / wedge-restart) | Disk fills, error storm, stalled loop, guard code tampered | `scripts/platformkit/ops_sentinel/` |
| Serving layer + kill switch + ops/health dashboard | Drawdown breach, stale feed, drift, going unnoticed | `api/main.py` (`/api/risk/status`, `/health/ops`) |
| One-command liveness harness (reports RED honestly) | A down subsystem rolling up green | `scripts/platformkit/proof_harness/system_proof.py` (fix `2eedc37e`) |
| Sanctioned single-PID restart, verified twice | A fleet that cannot come back after a bounce | `scripts/daemon_watchdog.py`; runtime `data/frontend/ops/post_restart_verify.json` (local-only) |

---

## Reproduce (per-file only)

Run the readout and the sentinel/subsystem tests individually -- never the full suite.

```
# One-command health readout: prints OVERALL RED/GREEN with the failing subsystems named
python -m scripts.platformkit.proof_harness.system_proof

# Sentinel tests (each watcher has its own test file)
python -m pytest scripts/platformkit/ops_sentinel/test_heartbeat_coverage.py -q
python -m pytest scripts/platformkit/ops_sentinel/test_guard_integrity.py -q
python -m pytest scripts/platformkit/ops_sentinel/test_disk_space.py -q

# Alerting subsystem: rate-limit, dead-letter queue, circuit breaker
python -m pytest scripts/execute_loop/tests/test_L22_alerting.py -q

# Ledger concurrency: the two-OS-subprocess race that proves the lock actually closes
python -m pytest scripts/platformkit/test_clv_ledger_io.py -q
```

On a fresh clone the private runtime artifacts under `data/` are absent, so the harness reports
the sections it can compose and marks the rest pending rather than fabricating a green.

---

## Why this matters to an employer

For a platform, infrastructure, or SRE-adjacent role, the interesting question is never "did it
work in the demo" -- it is "what happens at 3am when it doesn't, and no one is watching." This
stack is the answer: supervised processes that relaunch, an alert path hardened against its own
failure modes, a ledger that stays intact under concurrent writers, sentinels that watch the
watchers, and a single health command whose defining feature is that it will tell you the truth
when things are broken. The load-bearing decision was to treat a decorative green as a bug and an
honest red as correct behavior -- and to ship the commit that enforces it. That instinct, that an
unattended system's first job is to fail visibly, is the reliability skill the rest of the stack
is built to demonstrate.

---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](../INDEX.md) - [Home](../../README.md) - [Glossary](../GLOSSARY.md)
