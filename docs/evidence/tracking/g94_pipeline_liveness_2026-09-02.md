# G94 pipeline liveness

## Verdict

ACCEPT. The workstation bridge supervisor now publishes a PID and a
timestamped status snapshot. `bridge_liveness` uses `os.kill(pid, 0)`, never a
command-line search, to distinguish a dead supervisor from an idle one. A
snapshot older than 300 seconds is UNKNOWN, never a cached healthy value.

## Measured premise

At 2026-09-02 16:39 local time, the running workstation supervisor was PID
17780. Its `bridge_supervisor_status.json` reported all seven lanes as
`alive: true`, but had neither `written_at` nor a PID file. The status artifact
therefore could not distinguish a running idle supervisor from a dead one.

## Staleness budget and states

The budget is 300 seconds: three 90-second supervisor polls plus 30 seconds of
scheduler and filesystem grace. It is deliberately a liveness budget, not a
claim that a blocking queue refill completed. When a live PID has an expired
snapshot the checker reports UNKNOWN and does not restart it. A missing or dead
PID is DOWN even when a stale snapshot still says its lanes are alive.

The following commands exercised the actual `bridge_supervisor` program in an
isolated temporary working directory with no queues. They did not touch the
production supervisor, bridge workers, stage directory, or pod.

```text
DOWN transcript (actual bridge_supervisor --once has stopped)
state=DOWN pid=none status_age_seconds=0.3/300 reason=pid missing or not alive

UP transcript (actual isolated bridge_supervisor pid=28088)
state=UP pid=28088 status_age_seconds=3.2/300 reason=pid alive and status fresh

healthy restart transcript
state=UP pid=28088 status_age_seconds=3.5/300 reason=pid alive and status fresh
restart=no-op

STALE transcript (actual isolated bridge_supervisor pid=14532, live pid with 301-second-old status)
state=UNKNOWN pid=14532 status_age_seconds=301.4/300 reason=status older than 300s
```

## Restart boundary

`restart_if_down` only starts the local `bridge_supervisor` when its PID is
known DOWN. It never kills a process. Its source contains an explicit boundary:
it has no SSH, pod command, or pod kill path; the pod track daemon and every pod
process are out of scope. The UP transcript shows the required healthy no-op.

## Partial-upload decision

No `.part` reaper is added. `track_daemon.py` defines only plain `.mp4` as a
complete upload and the bridge atomically renames its `.mp4.part` temporary
file, so an abandoned partial cannot be mistaken for a complete staged video.
Deleting partials needs an independent retention and retry policy and would be
an unnecessary destructive action in this liveness row. The completion contract
and its prohibition on size-stability polling are unchanged.

## Verification

Focused test:

```text
python -m pytest scripts/platformkit/test_bridge_liveness.py -q
2 passed in 0.65s
```

Reader sweep found `night_report.py` as the sole consumer of
`bridge_supervisor_status.json`; it now renders expired lane state as UNKNOWN.
The new checker is also a reader and applies the same 300-second refusal.

### Verifier-contract B self-check

| Check | Result |
|---|---|
| B1 circular metric | Not applicable; the three states come from PID and wall-clock inputs, with none excluded. |
| B2 non-additive schema | `written_at` is additive; the only existing reader was updated and checked. |
| B3 fall-through loss | No queue or upload routing changed. |
| B4 re-claim loop | No claim or retry path changed. |
| B5 pre-verification deploy | No pod files or processes were touched. |
| B6 orphans | New module has its direct focused test and module invocation. |
| B7 head-slice evidence | Not applicable; this is three exhaustive state cases, not sampled renders. |
| B8 self-fit as independent | Not applicable; no fitted metric. |
| B9 degenerate denominator | Not applicable; state classification has no recycled denominator. |
| B10 moved bar | No harness threshold changed; the 300-second status budget is new and documented above. |

## NOT VERIFIED

- No production supervisor restart was performed; the existing bridge lanes
  stayed undisturbed.
- No pod process was inspected, killed, restarted, or deployed.
- No abandoned `.part` file was deleted or reaped.
- Master-worktree re-run and archive landing remain verifier actions under
  `VERIFIER_CONTRACT.md` A1 and A6.

Evidence paths verified at authoring time: this memo,
`scripts/platformkit/bridge_supervisor.py`,
`scripts/platformkit/bridge_liveness.py`,
`scripts/platformkit/night_report.py`, and
`scripts/platformkit/test_bridge_liveness.py` all exist in this worktree.
