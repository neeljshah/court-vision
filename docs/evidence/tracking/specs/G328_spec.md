GAP G328 | sport all | worktree a6 | log cx_g328_daemon_worker_accounting

**TOOLING ROW. `src/`, `domains/`, `api/`, `kernel/` and `intel/` are READ and IMPORT only. Build in
`scripts/platformkit/` (the daemon lives there: `scripts/platformkit/track_daemon.py`, `track_daemon_done.py`,
`track_daemon_ledger.py`, `track_daemon_sources.py`). NEVER edit a committed evidence hash, a committed
evidence artifact, `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`, or any threshold.**

**WHERE THIS ROW RUNS:** LOCAL for code and tests; the pod is READ-ONLY for the measurement
(`ssh -F ~/.ssh/config.pod pod`; NEVER stop, signal, restart or reconfigure `track_daemon` (pid 1168432,
`--workers 8 --forever`, launched 09:14Z with `PYTHONPATH=/workspace/nba-ai-system`) or `vol_guard.py`
(pid 1039858); NEVER write on the pod; never deploy). The daemon on the pod runs the PRE-G329 code; master
carries the G329 fix undeployed -- state that in the memo and build on master's version.

**WHY THIS ROW EXISTS.** `track_daemon.py` `tick()` (around lines 363-366 on the 2026-09-08 tree; re-cite)
counts only non-adjudicating jobs against `--workers`, so a job that finished tracking and moved to
adjudication (a threaded pandas concat over the clip's tables) keeps burning CPU while its worker slot is
already handed to the next clip. On 2026-09-07 the log showed '17 active' / '18 active' at `--workers 16`,
and the container is a 27.2-core cgroup quota (`cpu.cfs_quota_us 2720000 / period 100000`) that other
lanes' scorers share (S308 measured 0.14 of a core while the fleet ran). With `--workers 8` the daemon
delivers the same clips per hour as 16 at half the latency (measured 2026-09-07); whether adjudication
CPU is the reason is the question.

**PREMISE (step 0, BINDING before-condition):** from the daemon logs on the pod
(`/workspace/track_daemon_2026-09-08a.log`, `_2026-09-08b.log`, and any older ones present; read-only),
count the ticks whose reported 'N active' exceeds `--workers` for that daemon instance (identify the
`--workers` value per instance from the launch line or `ps`). **PRINT the table with n (ticks over,
ticks total, per instance). If no instance ever reports active > workers, the premise is FALSE: STOP,
write the memo, commit, report PREMISE FALSE.**

METHOD:
  1. **ACCOUNTING TRACE.** Cite with `file:line` where a job leaves the worker count, where adjudication
     starts and ends, what runs in the adjudication thread, and where the ledger row is written.
  2. **MEASURE (pod, read-only).** For every ledger row written today (2026-09-08) that carries timing
     fields, derive per clip: tracking wall seconds, adjudication wall seconds (from the row fields or the
     log lines: 'tracked rows=' -> row write), rows, and the concurrency of adjudications (how many clips
     were adjudicating at once) from the log timeline. If adjudication time is not recoverable from the
     rows, reconstruct it from log timestamps and say so. Report distribution (median, p90, max) with n,
     and the share of daemon CPU-seconds spent in adjudication if `/proc` stats of the workers allow a
     read-only sample over 10 minutes (say which method).
  3. **ADDITIVE CAP.** Under `scripts/platformkit/`, an opt-in `--adjudication-slots N` (default = no cap,
     behaviour unchanged) implemented as a counting semaphore around the adjudication step, OR counting
     adjudicating jobs against `--workers` behind a flag (say which and why). Existing flags, defaults,
     ledger fields and statuses keep their names and meanings (B2). No default changes.
  4. **TEST.** A per-file test with a fake tracker + fake adjudicator that pins: without the flag, the
     active count can exceed workers (the premise, reproduced on a construct); with the flag, it cannot;
     the ledger row is unchanged in either mode.
  5. **BEFORE/AFTER ESTIMATE, NOT A CLAIM.** From step 2's numbers, estimate clips/hour and latency at
     8 workers with and without the cap on the 27.2-core quota, labelled as an ESTIMATE from measured
     per-clip CPU; the actual before/after requires a deployment this row does NOT perform.
  6. **CHANGE NOTHING ELSE.** No threshold, no committed hash, no register edit, no daemon interaction.

**HONEST LIMITATIONS to state, not discover:** the pod runs older daemon code than master; concurrency
reconstructed from logs is approximate to the log cadence; the cgroup is shared with other lanes'
scorers, so CPU-seconds attribute to the daemon only where /proc says so; no throughput claim is made
until the cap is deployed and measured.

ACCEPTANCE RULE:
  metric        = the premise table (ticks active > workers, n); the trace with `file:line`; the per-clip
                  adjudication timing distribution with n and method; the flag + test; the labelled
                  estimate
  before        = adjudicating jobs do not count against `--workers`; no adjudication cap exists;
                  '17 active' / '18 active' at `--workers 16` (2026-09-07 log)
  bar           = the premise is reproduced from logs with n; the cap is opt-in and additive with a
                  passing per-file test; every timing cell carries n and its method
  n             = every tick in the daemon logs present on the pod; every 2026-09-08 ledger row with
                  timing (exhaustive; Q7)
  eye check     = NONE. Say that.
  must not move = the running daemon and guard; every flag default; every committed artifact; `src/`,
                  `domains/`, `api/`, `kernel/`, `intel/`; `data/`; anything on the pod;
                  `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`
  verdict       = **DONE** if the bar holds; **PARTIAL** with the explicit list otherwise.
EVIDENCE: `docs/evidence/tracking/g328_daemon_worker_accounting_2026-09-08.md` (<= 60 lines) with VERDICT
on line 1, the premise table, the trace, the timing table, the estimate, a **NOT VERIFIED** list, wall
time and the SHA-256s; plus `docs/evidence/tracking/g328_daemon_worker_accounting_2026-09-08/timing.csv`
(integer cells zero-padded to 6 digits) and the raw log-derived tick table. **ADD ONE RESULTS_LEDGER.md
ROW IN THE SAME COMMIT** (one `>>` append). **Do NOT edit `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.**
TEST: `tests/platformkit/test_g328_daemon_worker_accounting.py` -- the construct of step 4. Run that ONE
file and the existing daemon test files (`scripts/platformkit/test_track_daemon.py`, `test_track_daemon_done.py`,
`test_track_daemon_ledger_denominator.py`, `test_track_daemon_job_budget.py`, `test_track_daemon_timeout_verdict.py`,
`tests/platformkit/test_g329_degenerate_resume.py`) each individually. **NEVER a full pytest.** Every
touched file <= 300 lines (`track_daemon.py` is at 440 on the allowlist: do not grow it; put the cap in a
new module and call it with a few lines).
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
