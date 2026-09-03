# G182: calibration_unavailable cause funnel

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` (A2, A3, A7, Q8;
Section B self-check below). This is a diagnostic-only tennis measurement. It
does not alter the adapter, solver, CameraLock, drift threshold, any bar, the
coordinate contract, or any prior verdict. The coverage adjudication is not
re-opened and no remedy is proposed.

## Q8 premise first

Before this run, the committed G161 labels and G175 retained manifest were
parsed independently. The label input has 113 unique `RALLY_VIEW` frames and
187 unique `NOT_RALLY` frames; all 300 join to distinct manifest frames. The
G175 premise reproduces exactly: `calibration_unavailable` is 104 / 113 =
92.04% in `RALLY_VIEW`, versus 170 / 187 = 90.91% in `NOT_RALLY`.

## Quoted condition chain

`process_video` makes the returned calibration status the per-frame status
only if no homography is returned:

```python
# domains/tennis/tracking/adapter.py:223-247
if evaluated:
    homography, provenance, calibration_status, drift, evidence_count = self._calibrated_homography(frame)
    player_count = 0
    if homography is not None:
        # player work omitted
    status = (calibration_status if homography is None else
              "emitted_players" if player_count else "no_complete_player_pair")
```

The adapter calls corner detection first. A missing result returns no fresh
homography. With corners, all three following conditions also return no fresh
homography: no temporal result homography, a temporal `recompute`, or a failed
comparison against the prior `self._homography`.

```python
# domains/tennis/tracking/adapter.py:146-170
corners = self.detect_court_corners(frame)
self._last_fresh_corners = None
if corners is None:
    self._lost_corner_frames += 1
    if self._lost_corner_frames > 30 and not self._camera_lock.ready:
        self._reset_temporal_calibration()
    self._calibration_provenance = "unavailable"
    return None
self._lost_corner_frames = 0
detections = {name: (float(point[0]), float(point[1]), 1.0) for name, point
              in zip(("doubles_bl", "doubles_tl", "doubles_br", "doubles_tr"), corners)}
result = self._calibrator.update(detections)
if result.homography is None or result.recompute or not self._in_tolerance(result.homography, frame.shape[:2]):
    self._calibration_provenance = "unavailable"
    return None
self._corners, self._homography = corners, result.homography
self._last_fresh_corners = corners
return self._homography

result = self._camera_lock.resolve(frame, self._stable_homography(frame), self._last_fresh_corners)
```

`self._corners` is only freshly assigned after all three temporal conditions
pass; its absence is not itself read as a status condition here.
`self._homography` is consulted by `_in_tolerance`; when it is absent,
`_in_tolerance` returns `True` (adapter.py:132-139), so absence of that field
does not by itself produce this status. The `TemporalCalibrator` is consulted
before the CameraLock. Its `update` returns its previous good homography on a
missing raw fit, and otherwise marks `recompute` when the temporal error is
over its configured threshold (keypoint_calib.py:176-195).

CameraLock is the final consultation. It can return an accepted old lock even
when there are no current corners; a rejected ready old lock without a fresh
solve returns `unsolved_drift`, not `calibration_unavailable`.

```python
# domains/tennis/tracking/camera_lock.py:186-205
if fresh is not None:
    self.add_fresh_solve(fresh)
if self.ready:
    check = (drift_from_corners(self.homography, corners) if corners is not None
             else drift_from_frame(self.homography, frame))
    drift = float(check.residual_px) if check.residual_px is not None else float("nan")
    if self.accepts(check, frame.shape[0]):
        return (fresh if fresh is not None else self.homography,
                "solved" if fresh is not None else "camera_lock_drift_checked",
                "ready", drift, check.evidence_count)
    self.reset()
    if fresh is not None:
        self.add_fresh_solve(fresh)
        return fresh, "solved", "ready", drift, check.evidence_count
    return None, "unavailable", "unsolved_drift", drift, check.evidence_count
if fresh is not None:
    check = drift_from_corners(fresh, corners)
    drift = float(check.residual_px) if check.residual_px is not None else float("nan")
    return fresh, "solved", "ready", drift, check.evidence_count
return None, "unavailable", "calibration_unavailable", float("nan"), 0
```

Therefore the exact final condition is: `_stable_homography(frame)` supplied
`fresh is None` and `CameraLock.ready` is false. The earliest point at which a
frame loses its fresh calibration path is `detect_court_corners(frame)`
returning `None`; the earliest point at which it is doomed specifically to
`calibration_unavailable` is the final quoted CameraLock branch, because a
ready, accepted lock can still reuse a prior homography after that first loss.

## Exhaustive read-only pod funnel

The opt-in, unlanded harness is
`scripts/platformkit/tracking/g182_calibration_funnel.py`. It wrapped methods
only in the measurement process, read the existing 38,094,576-byte pod clip
`data/videos/tennis_smoke.mp4`, and wrote a temporary result store under
`/tmp`. No source file was copied to the pod checkout or deployed. The run
decoded every frame once: **N = 28,773** unique source frames, indexed 0
through 28,772. Its committed raw per-frame observations are
[`g182_funnel.json`](g182_funnel/g182_funnel.json).

Every row supplies a count and its eligible denominator.
`candidate_homography` means `TemporalCalibrator.update` returned a matrix
before the adapter's `recompute` and `_in_tolerance` condition. `homography`
means the adapter actually returned a fresh stable homography. CameraLock is
an all-frame fallback consultation, so its eligible denominator is all decoded
frames, not only the fresh branch.

| Stage | Count / eligible denominator | Share of eligible | Share of all decoded |
|---|---:|---:|---:|
| decoded | 28,773 / 28,773 | 100.00% | 100.00% |
| reaching corner detection | 28,773 / 28,773 | 100.00% | 100.00% |
| enough corners | 2,660 / 28,773 | 9.24% | 9.24% |
| temporal candidate homography | 2,660 / 2,660 | 100.00% | 9.24% |
| fresh stable homography | 2,098 / 2,660 | 78.87% | 7.29% |
| CameraLock returns a homography after lock/drift handling | 2,522 / 28,773 | 8.77% | 8.77% |
| emitting players | 2,487 / 2,522 | 98.61% | 8.64% |

The CameraLock row is not a false sequential continuation of fresh solves:
414 of its 2,522 accepted returns had no current corners and reused a prior
lock. They remain counted rather than excluded. Of the 2,660 frames with
current corners, 2,108 reached a non-`None` CameraLock result; 2,098 had a
fresh stable homography and 10 used a valid lock reuse after the adapter did
not return a fresh one.

## Located wall

**Corner detection is the wall.** The single largest direct-chain loss is
between reaching corner detection and returning enough corners: 26,113 /
28,773 = **90.755%**. This is a complete, exhaustive clip denominator, not a
selected status subset. No later loss is close: the fresh-stability condition
loses 562 / 2,660 = 21.128% of frames that already have corners, while only
35 / 2,522 = 1.388% of lock-resolved frames fail to emit a player pair.

## Evenly sampled eye check

The largest-loss decision set contains all 26,113 frames that reached corner
detection but returned no corners. Sorted by source index, inclusive evenly
spaced positions 0, 6,528, 13,056, 19,584, and 26,112 yielded frames 0,
7,124, 14,283, 21,402, and 28,772. These are not a head slice.

| Frame | Render | Eye observation |
|---:|---|---|
| 0 | [render](g182_funnel/renders/frame_00000_enough_corners.jpg) | Tight player close-up; no court geometry is visible. |
| 7,124 | [render](g182_funnel/renders/frame_07124_enough_corners.jpg) | Tight player close-up with scoreboard; no court geometry is visible. |
| 14,283 | [render](g182_funnel/renders/frame_14283_enough_corners.jpg) | Low oblique view includes a partial near court and crowd, but not the full doubles rectangle or four court corners required by this adapter. |
| 21,402 | [render](g182_funnel/renders/frame_21402_enough_corners.jpg) | Tight player close-up; no court geometry is visible. |
| 28,772 | [render](g182_funnel/renders/frame_28772_enough_corners.jpg) | Player crop with only a small near-line fragment; the four-corner court is not visible. |

None of the five evenly spaced frames is obviously calibratable under the
adapter's four-corner input contract. The lone wider sample still lacks the
full court boundary needed for its corner solver. This supports the measured
conclusion that corner detection is unrecoverable on this footage for the
current contract; it does not prescribe a change.

## Reproduction and self-check

- **A2:** The committed `frame_records` were independently re-counted after
  collection: 28,773 records, 28,773 unique frames, range 0..28,772. Every
  reported stage count and the 26,113 / 28,773 largest loss reproduced from
  that artifact. The pod adapter SHA-256 recorded in the artifact is
  `c7314449ddccc9f27868ea5a20dbbe8458c96d9a4678b9597dc4b585708fcc58`.
- **A3 / B7:** All five required renders are inclusive evenly spaced samples
  over the complete 26,113-frame winning loss set.
- **A7:** Before commit, this memo, the raw JSON, all five linked renders, and
  the unlanded harness plus focused test were checked for existence.
- **B1:** Clear. The decoded-frame denominator is exhaustive; no failed or
  emitted row was excluded. The CameraLock fallback branch is explicitly
  counted with its all-frame eligible denominator.
- **B2:** Clear. No production schema, status, field, reader, or alias changed.
- **B3:** Clear. This measurement only observes existing branches; it changes
  no gate or fall-through behavior.
- **B4:** Clear. No claim, queue, retry, or ownership behavior changed.
- **B5:** Clear. The harness ran inline under `nohup`; no file was copied to
  the pod checkout and no deployment occurred.
- **B6:** Clear. No module, import, test, or command was moved or retired.
- **B8:** Clear. This is direct stage observation, not a fitted residual or an
  independent accuracy claim.
- **B9:** Clear. The unit is one unique decoded source frame.
- **B10:** Clear. The harness is additive and made no threshold, bar, solver,
  lock, or coordinate-contract change.

## NOT VERIFIED

- A different footage source, camera angle, encode, or court-corner provider.
- Any remedy, threshold change, solver change, lock change, or coverage-bar
  adjudication.
- A human ground-truth label for every one of the 26,113 corner-loss frames;
  the required five-frame evenly sampled eye check is not a relabelling pass.
- Any downstream tracking-quality or prediction conclusion beyond this
  calibration-unavailable cause funnel.
- The working pod's current unlanded harness file: execution used an inline
  process-only copy, while the committed harness is retained locally for
  reproduction. No pod deployment was performed.
