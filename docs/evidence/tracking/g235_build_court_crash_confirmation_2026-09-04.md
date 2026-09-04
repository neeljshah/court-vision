# G235: `_build_court` crash confirmation attempt

**Verdict on the proposed zero-dimension guard: INSUFFICIENT.** The required
unguarded daemon-equivalent route did not reproduce the historical `cv2.error`
in `_build_court`; it successfully constructed the court and entered the frame
loop. Per `docs/evidence/tracking/specs/G235_spec.md`, the guarded rerun was not
performed. This is one existence draw on a shared, non-deterministic route, not
a contradiction of the nine historical failures. It means the guard was not
exercised and is not confirmed.

This memo follows `docs/evidence/tracking/VERIFIER_CONTRACT.md`. No production
source, pod checkout, daemon, keeper, threshold, harness, coordinate contract,
`CLIP_SPORTS`, corpus source, or legacy basketball table was changed.

## Machine, hold, and source identity

Measurement machine: the pod at `/workspace/nba-ai-system`, because the daemon
route, exact corpus source, OpenCV 5.0.0 runtime, and resident models exist only
there. The route was dispatched in one process so `_build_court` could be
monkey-patched without writing `src/`:

```text
scripts/run_clip.py --video /workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4 --game-id g235_reproduction --no-show --frames 3000 --data-dir /workspace/nba-ai-system/data/tracking/g235_reproduction_20260904
```

At `2026-09-04T06:38:58.736678+00:00`, an exact `/proc` check found zero
G232/G233 Python processes. It matched the Python executable plus the named
G232/G233 command argument, not a command-line substring. The two-lane hold was
clear. Permanent residents were not waited on, stopped, or restarted.

| Input fact | Literal observation |
|---|---|
| Source path | `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4` |
| Bytes | 2,931,985,407 |
| Resolution | 1920x1080 |
| Frames / rate | 174,430 / 30/1 |
| `scripts/run_clip.py` SHA-256 | `7aec5d57e0357ff4585deabeb7a18bbc5bcb2c197cefe5fad591c16ca3bc761b` |
| `src/pipeline/unified_pipeline.py` SHA-256 | `047dd04e9b12b588c560f68dbab32aa1855f791c2e1a46f19f4e082f50c4f331` |
| `scripts/platformkit/track_daemon.py` SHA-256 | `204a892086e9c62a66ff2e9789fa31033f316c7cafc7d548a3e09e0b80da5ada` |

## Disk guard and cleanup

`df` was not used. Each launcher attempt ran `dd if=/dev/zero ... bs=1M count=4
conv=fsync` before it created a new G235 tracking directory.

| Attempt | Pod data `du -sm` before probe | Probe | Cleanup result |
|---|---:|---|---|
| Instrumentation-launch error, 2026-09-04T06:41:57Z | 32,013 MB | Passed | Temporary root removed; recorded expected freed size 786 bytes. No tracking output was created. |
| Valid unguarded route, 2026-09-04T06:42:56Z | 32,021 MB | Passed | Cleanup receipt: temporary root 14,544 bytes plus tracking directory 531 bytes; expected freed total 15,075 bytes. Both paths were later verified absent. |

The valid route was interrupted only after `_build_court` had succeeded. SIGINT
was sent to the sole Python process whose executable was Python and whose
environment contained the exact new `G235_DATA_DIR`; no other process was
matched or signalled. A later pod data census was 32,042 MB, which is not
interpreted as a G235 delta because permanent services are active.

Both local retrieval bundles were deleted after their facts were copied here:
863 bytes from the invalid launcher and 15,158 bytes from the valid launcher,
for 16,021 local temporary bytes freed. No local run artifact is cited as
evidence.

## Reproduction result and observed state

The valid unguarded launch ran about 30 seconds and did not die in
`_build_court`. Its route log recorded this branch (ASCII punctuation here
preserves the logged dimensions):

```text
_build_court: rectified portrait (1711x3404) - rotated 90 deg -> landscape (3404x1711)
Pano cache hit: pano_wnba__wnba_01.png
[unified_pipeline] Using static Rectify1.npy for 'wnba__wnba_01.mp4'
 Frame 948...
```

The process-only observer serialized its state before `cv2.resize`; the run was
then stopped at frame 948 with SIGINT. The captured exception is the requested
stop (`KeyboardInterrupt` in `ball_detect_track.py`), not a `_build_court`
exception. At `_rh, _rw = rectified.shape[:2]`, the unrotated rectification had
height 3404 and width 1711; the existing portrait branch selected width 3404 and
height 1711. The candidate zero-dimension condition was false on this draw.

| Required state | Observation for this run |
|---|---|
| `rectified.shape` at a failure | No failure occurred. At successful `_build_court` return it was literally `[3404, 1711, 3]`. |
| `rectified.dtype` | `uint8` at successful `_build_court` return. |
| `_rw`, `_rh` at `cv2.resize` | 3404, 1711 after existing portrait rotation. |
| `map_img.shape` / dtype | `[695, 1241, 3]`, `uint8` at successful `_build_court` return. |
| `_pano_ok` | Literally `true`. |
| Existing fallback fired | None of the three 940x500 default fallbacks. Portrait rotation fired and returned a valid landscape size. |
| Crash signature | Not reproduced. No `cv2.error` at `_build_court`. |
| Rows / harness stage | No completed table and no harness result. The required stop prevented a guarded run and tracking completion. |

The first launcher attempt is not counted as the G235 reproduction: its
in-process source insertion failed before `run_clip` began. It is recorded only
to account for its successful disk probe and cleanup. The second launch is the
single valid unguarded existence draw.

## Guard experiment and verdict

**The proposed guard is INSUFFICIENTLY VALIDATED, not CONFIRMED and not WRONG.**
The observed rectification was nonzero and no crash occurred, so the candidate
condition was never reached. The historical crash may be intermittent; one draw
cannot show zero dimensions were absent in the nine historical failures, nor can
it show this guard fixes them.

The spec requires stopping immediately when the unguarded route does not crash.
Accordingly, the guarded monkey-patched rerun was not run. The process-only
launcher contains the candidate runtime replacement, but it was never invoked
for this result and no patch was left in `src/` or deployed.

## MLB empty-tail loose end

The cheap ledger check found one MLB thin row in
`/workspace/nba-ai-system/data/tracking/track_daemon_ledger.jsonl`:

```text
game_id: mlb_gDv5xF2AA2E
status: thin
rows: 0
seconds: 1550
decoded_frames: null
tail: ""
failure_heads: []
```

Its tracking directory exists and is not empty: `tracking_data.csv` is
21,642,338 bytes; `teacher_meta.json` is 7,219 bytes;
`tracking_capability.json` is 63 bytes; and `harness_verdict.json` is 347 bytes.
This characterises the empty tail as a terminal logging gap rather than absence
of emitted files. It does not establish the underlying MLB cause. Nothing there
was edited or deleted.

## Verifier self-check and NOT VERIFIED

- B1: No filtered metric or denominator claim. The run count is one valid
  unguarded existence draw.
- B2-B4: No schema, status, gate, reader, or claim path changed.
- B5: No pod code was copied, deployed, bootstrapped, or retained.
- B6: No module was moved or retired.
- B7-B9: No render, fitted residual, coverage, or row-quality metric is claimed.
- B10: No threshold, harness configuration, contract, or bar changed.
- A7: This required evidence path exists before commit.

Not verified: every captured state at an actual failure; whether a degenerate
dimension occurred on any historical failure; a guarded completion and row
count; a harness stage; production behavior on every path; tracking correctness;
and the underlying MLB empty-tail cause. A runtime-only guard would demonstrate
behavior for one path, not correctness of a future human production change in
every path.
