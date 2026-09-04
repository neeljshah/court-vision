# G243: Amateur Fixed-Camera Seeded Calibration

**GATE: NOT RUN - FALSIFIED SOURCE PREMISE (n=0 decodable clips, 0 seeds, 0 of 3 labellings).**

## Verdict

**FALSIFIED / CLOSED BEFORE MEASUREMENT.** The exact required corpus source does not exist at either the worktree-relative target or the declared pod corpus path. It is therefore impossible to select a seed frame, make the three fresh labels, fit a court, render the independent-geometry gate, propagate, or compute an in-court denominator without substituting a different source. No source was substituted.

This is the Q8 premise-first result for `docs/evidence/tracking/specs/G243_spec.md`, and follows `docs/evidence/tracking/VERIFIER_CONTRACT.md`. It changes no production code, label, court coordinate contract, matcher, daemon, keeper, corpus source, `src/`, or `domains/` file.

## Lane hold, machine, and source check

I began at 2026-09-04 04:40:26 -05:00 in `C:\Users\neelj\nba-track-a6` on branch `track-a6`, as the permitted second lane. Immediately beforehand, the exact executable-and-argument check found `pythonw.exe` PID 18132 running tag `g241b_seed_horizon_to_failure` with cwd `C:/Users/neelj/nba-track-a5`; it was not interrupted. Permanent residents were not touched.

The local machine was used for read-only source checks and the local disk probe. The pod was used only for one read-only `stat`/`ffprobe` source check because it is the declared corpus machine; no code or file was deployed to it.

| Required input | Full path opened | Result |
|---|---|---|
| Worktree target | `C:\Users\neelj\nba-track-a6\data\footage_corpus\g220c__jh3fnwMi7dM.mp4` | Absent; no byte size, resolution, duration, or frame count exists to report. |
| Shared local corpus check | `C:\Users\neelj\nba-ai-system\data\footage_corpus\g220c__jh3fnwMi7dM.mp4` | Absent; no byte size, resolution, duration, or frame count exists to report. |
| Declared pod corpus check | `/workspace/nba-ai-system/data/footage_corpus/g220c__jh3fnwMi7dM.mp4` | `stat` returned `No such file or directory`; `ffprobe` was consequently not run. |

The original relative target was checked first. The shared local and pod paths were narrowly checked read-only to rule out a worktree-only missing corpus. The premise remains falsified at every named source location.

## Disk guard and cleanup

`df` was not used. The local GNU `dd` guard ran before evidence files were written: `dd if=/dev/zero of=g243_disk_probe.bin bs=1M count=1 conv=fsync status=none` exited 0 and wrote 1,048,576 bytes. The exact probe was then removed; bytes freed: 1,048,576. The requested pod `du -sm /workspace/nba-ai-system/data` cannot establish available space for this row because the target file itself was absent; no measurement output was written there. No corpus source was deleted.

## Court-model inspection and unperformed gate

`scripts/platformkit/tracking/g196_homography_from_labelled_corners.py` defines exactly two accepted keys in `court_points_for_sport`:

| Key | Returned ordered near-paint corners, ft | Assumptions encoded by that module |
|---|---|---|
| `ncaa_basketball` | `[(19,0),(31,0),(19,19),(31,19)]` | 94 x 50 ft court, 12-ft lane, 19-ft paint depth. |
| `wnba` | `[(17,0),(33,0),(17,19),(33,19)]` | 94 x 50 ft court, 16-ft lane, 19-ft paint depth. |

There is no high-school key. I used **no key**: with no frame to inspect, the footage cannot confirm whether it is an 84 x 50 ft high-school court, and fitting either existing 94-ft model would silently assume the wrong court length for the stated target. Accordingly, no court extent was scored and no in-court fraction exists. Had the named footage been available and independently shown to be high-school geometry, the required scoring extent would have been 50 ft wide by 84 ft long with a 12-ft lane; that hypothetical was not applied to a substituted source.

No `select=eq(n,N)` decode occurred because there was no frame `N` to decode. No label was made, changed, repeated, or selected; therefore no per-point median/max spread can be compared with G140's 11.39 px p90, and there is no alternate-label RMS or verdict movement. No homography, fitted input, render, G222 match/inlier/RMS record, propagation horizon, detector projection, or labels-per-hour result exists. This is not a gate fail: it is an unrun gate caused by an absent mandatory input.

## G233d comparison

| Quantity | G233d broadcast WNBA | G243 amateur target |
|---|---:|---:|
| Exact source availability | Present | Absent at all named locations |
| Seed / gate | Frame 19599, PASS on independent arc and sideline | No frame, gate not run |
| Direct span | 1,200 frames | 0 frames |
| Direct RMS | 0.299365-0.702623 px | Not measured |
| In-court fraction | One detector draw, approximately 0.83-0.92 by band on 94 x 50 ft | Not measured; no court extent was scored |

No conclusion about whether amateur fixed-camera footage is easier or harder than broadcast follows from an absent input.

## Code identity and contract self-check

No route was exercised on the pod. The inspected local sources were `g196_homography_from_labelled_corners.py` SHA-256 `76ddb96f37982f24fd1a606d6b61b840863ffc973e94c0a0cc65342981b14d53` and `g222_direct_to_seed_propagation.py` SHA-256 `7788d31c7ae4f705af0ec494547a28e160fb6b3980c383a6896b932499cea450`.

Contract self-check: A7 names only this memo and its ledger row, both committed; B1 has no metric denominator beyond the explicitly named zero available inputs; B2-B6 change no schema, lifecycle, deployment, production module, or module location; B7 does not claim a render sample; B8 does not treat fitted points or construction-zero drift as evidence; B9 does not use a recycled unit; B10 changes no bar or matcher. Q does not apply to this tracking measurement row. Q8 is satisfied by the direct re-measurement of the named source premise before any scored metric.

## NOT VERIFIED

- Whether the named footage is actually an 84 x 50 ft high-school court; there was no footage to inspect.
- Any seed-render PASS or FAIL, label repeatability, court model fit, direct propagation, visual geometry, in-court fraction, detector behavior, or horizon.
- Whether a copy of this source exists under an unlisted path. Finding and approving a replacement source requires a new scoped row; it cannot be inferred here.
- Automatic calibration, which this row did not exercise.
