# G51 Pod Drift Check

## Scope and premise

This check compares the tracking-number producer module globs
`domains/*/tracking/*.py`, `scripts/platformkit/tracking/*.py`,
`scripts/platformkit/track_daemon*.py`, and
`scripts/platformkit/tracking_harness.py`. It excludes `test_*.py` files from
those globs. Master membership comes from Git-tracked files in the local master
worktree; pod membership comes from read-only `find` plus `md5sum`. The pod
command does not run Git and does not write, copy, deploy, restart, or signal a
process.

Before adding the check, the required direct read-only sweep found 16 DIFFERS,
5 POD-ONLY, and 0 MASTER-ONLY modules. The live final run below is the current
point-in-time result. Its changed membership is itself why this check is needed.

## Constructed acceptance cases

The single focused test plants all three named cases in known in-memory module
maps: `shared.py` has different MD5 values, `pod_only.py` exists only on the
pod, and `master_only.py` exists only on master. It then supplies an unreachable
SSH runner. The test asserts all three named output sets, `UNKNOWN`, and exit 0.

Command:

```text
python -m pytest scripts/platformkit/tracking/test_pod_drift.py -q
```

Result:

```text
1 passed in 0.88s
```

An additional direct unreachable check used `--host 127.0.0.1 --port 1` and
produced `UNKNOWN: pod drift check unavailable` with exit 0.

## Live pod run

Wall-clock time was 2.823 seconds, below the 20-second session budget. Output
below is verbatim from the live read-only run:

```text
== pod drift (tracking-number producer modules)
  DIFFERS (15)
    domains/baseball/tracking/geometry.py
    domains/basketball/tracking/line_calibration.py
    domains/football/tracking/clustering_diagnostic.py
    domains/football/tracking/geometry.py
    domains/football/tracking/line_probe.py
    domains/soccer/tracking/geometry.py
    domains/soccer/tracking/keypoints.py
    domains/tennis/tracking/court_lines.py
    scripts/platformkit/track_daemon.py
    scripts/platformkit/track_daemon_ledger.py
    scripts/platformkit/tracking/basketball_imagepx_features.py
    scripts/platformkit/tracking/football_fieldview.py
    scripts/platformkit/tracking/homography_eligibility.py
    scripts/platformkit/tracking/source_timebase.py
    scripts/platformkit/tracking_harness.py
  POD-ONLY (4)
    domains/baseball/tracking/pitch_view_gate.py
    scripts/platformkit/tracking/basketball_floor_gate.py
    scripts/platformkit/tracking/tennis_keypoint_train.py
    scripts/platformkit/tracking/tennis_vertical_probe.py
  MASTER-ONLY (0)
    (none)
```

## NOT VERIFIED

- This row identifies module/hash drift only; it does not attribute each
  difference to a source or determine whether it is correct.
- The live sets are a point-in-time observation and can change while independent
  24/7 pod work is active.
- The unlanded script was not run through the existing hard-coded master
  `loop_status.sh`; doing so would require copying it to that tree, which this
  row does not authorize. The direct invocation used the same helper and
  arguments that the appended status line uses.
- No pod file, daemon, capture process, or deployment state was changed.
