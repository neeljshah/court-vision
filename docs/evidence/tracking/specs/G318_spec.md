GAP G318 | sport all | worktree a1 | log cx_g318_probe_status

**TOOLING ROW. `src/`, `domains/`, `api/`, `kernel/` and `intel/` are READ and IMPORT only. Build in
`scripts/platformkit/` (`track_daemon.py`, `track_daemon_sources.py`, `tracking/source_timebase.py`).
NEVER edit a committed evidence hash, a committed evidence artifact,
`docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`, or any threshold.**

**WHERE THIS ROW RUNS:** LOCAL for code and tests; the pod is READ-ONLY for the census (`ssh -F
~/.ssh/config.pod pod`; NEVER stop, signal, restart or reconfigure `track_daemon` (pid 1168432) or
`vol_guard.py` (two instances, pids 1039858 and 1201700); NEVER write on the pod; never deploy). The pod
daemon runs pre-G329 code; master carries the G329 fix undeployed -- build on master.

**WHY THIS ROW EXISTS.** `scripts/platformkit/tracking/source_timebase.py` `probe_source()` always returns
a truthy 5-key dict, so `track_daemon.py`'s `if source:` is always true and a FAILED ffprobe and a
NEVER-PROBED source both surface as identical null fields in the ledger row. The census on 2026-09-07
found 0 occurrences (latent), but G329 then found 8/22 degenerate rows classified `preflight_reject` and
8/22 `runner_absent` whose cause could not be told apart from the row alone, and 4/22 with no tail at all.
An explicit `probe_status` on every row (`ok` / `failed:<reason>` / `not_probed`) is the missing field.

**PREMISE (step 0, BINDING before-condition):** show from the code (`file:line`) that `probe_source()`
cannot return a falsy value on ffprobe failure, and run it locally against a non-existent path and a
zero-byte `.mp4`: PRINT both return values. Then census the pod ledger (read-only `cat`): count rows whose
timebase fields are all null, with n. **If `probe_source()` returns a falsy value on failure, the premise
is FALSE: STOP, write the memo, commit, report PREMISE FALSE.**

METHOD:
  1. **TRACE.** Cite where the probe runs, what it returns on each failure path (missing file, ffprobe
     rc != 0, no video stream, unparsable rate), where the daemon consumes it, and where the ledger row is
     written.
  2. **ADDITIVE FIELD.** `probe_status` written by the daemon on EVERY new ledger row: `ok`,
     `failed:<short reason>` (missing, ffprobe_rc, no_video_stream, parse), or `not_probed`. Existing
     fields keep names and meanings (B2); `probe_source()` keeps its return shape and gains an additive
     `status` key (never a falsy return: callers already branch on truthiness). No default changes.
  3. **CENSUS RE-READ.** Re-classify the pod ledger's all-null-timebase rows (from step 0) by what the
     surviving data dir / source file says (read-only): source absent, source present but unprobeable
     (run ffprobe read-only on the pod on up to 20 of them; state n), or unknown. Table with n.
  4. **TEST.** One per-file test: a failing ffprobe (stub) yields `probe_status=failed:...` with the
     timebase fields null and the row still written; a missing file yields `failed:missing`; a good probe
     yields `ok`; `not_probed` when the daemon skips the probe.
  5. **CHANGE NOTHING ELSE.** No threshold, no committed hash, no register edit, no daemon interaction,
     no deployment.

**HONEST LIMITATIONS to state, not discover:** the pod daemon will not write the field until the
undeployed master daemon is shipped; the census re-read classifies by what survives today, not by what
the daemon saw at the time.

ACCEPTANCE RULE:
  metric        = the premise prints and code cite; the pod census (all-null rows, n) and its re-read
                  table; the field + test
  before        = `probe_source()` is always truthy; ledger rows cannot distinguish never-probed from
                  probe-failed; no `probe_status` field exists
  bar           = every new-row path writes `probe_status`; the test covers the four values; every census
                  cell carries n; 0 existing fields renamed; `track_daemon.py` does not grow past its 440
                  allowlist (put logic in `source_timebase.py` or a new module)
  n             = every ledger row on the pod (exhaustive; Q7)
  eye check     = NONE. Say that.
  must not move = the running daemon and guards; every flag default; every committed artifact; `src/`,
                  `domains/`, `api/`, `kernel/`, `intel/`; `data/`; anything on the pod;
                  `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`
  verdict       = **DONE** if the bar holds; **PARTIAL** with the explicit list otherwise.
EVIDENCE: `docs/evidence/tracking/g318_probe_status_2026-09-08.md` (<= 60 lines) with VERDICT on line 1,
the premise prints, the census tables, a **NOT VERIFIED** list, wall time and the SHA-256s; plus
`docs/evidence/tracking/g318_probe_status_2026-09-08/census.csv` (integer cells zero-padded to 6 digits).
**ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT** (one `>>` append). **Do NOT edit
`docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.**
TEST: `tests/platformkit/test_g318_probe_status.py`. Run that ONE file and the existing test file of every
touched module (`scripts/platformkit/test_track_daemon.py`, `test_track_daemon_done.py`, and any
`source_timebase` test) each individually. **NEVER a full pytest.**
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
