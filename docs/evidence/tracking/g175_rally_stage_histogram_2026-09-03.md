# G175: rally-view stage histogram

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` (A2, A3, A7,
Q8; Section B self-check below). This is a read-only join of a retained
per-frame manifest to G161's committed labels. It does not revisit the
coverage bar, change an adapter or solver, alter a threshold or label, build a
classifier, or move any verdict.

## Q8 premise and exact artefact joined

The premise is confirmed. G161's committed label artefact is
[`g161_rally/labels_pass1.csv`](g161_rally/labels_pass1.csv): 300 unique,
systematically spaced labels over source indices 56 through 28,733, with 113
`RALLY_VIEW` labels. It labelled the **2,024,970,178-byte encode** that became
`data/videos/reference/tennis.mp4` at 09:45:18.

The status artefact joined here is the G152b sidecar
`%TEMP%\\g152b_tennis_reference_20260903\\frame_manifest.csv`, preserved for
this evidence as
[`g175_stages/g152b_38mb_frame_manifest.csv`](g175_stages/g152b_38mb_frame_manifest.csv)
(SHA-256 `6ad4a22268ee4865a8a5ab0dc28e0d3f6e852e9af33d69d5e811a22c7bd82bea`).
It was produced from the **38,094,576-byte encode** measured by G152b, not
from G161's 2 GB encode.

The encodes are not byte-identical, and the reference path was overwritten;
that distinction is material. Both sequentially decode 28,773 frames. The
joined manifest has exactly 28,773 unique `frame` values, 0 through 28,772;
all 300 committed G161 indices occur exactly once. Thus this is an
index-commensurable join of the G152b status measurement to the G161 labels,
not a claim that the two files are the same artefact.

## Histogram

Eligible denominator: **all 113 committed G161 `RALLY_VIEW` labels**. The
contrast column is the separate 187 committed `NOT_RALLY` labels. Shares use
their own named column denominator; no row with a failing status was removed.

| Per-frame `status` | RALLY_VIEW count / 113 | RALLY_VIEW share | NOT_RALLY count / 187 | NOT_RALLY share |
|---|---:|---:|---:|---:|
| `calibration_unavailable` | 104 / 113 | 92.04% | 170 / 187 | 90.91% |
| `emitted_players` | 8 / 113 | 7.08% | 15 / 187 | 8.02% |
| `unsolved_drift` | 1 / 113 | 0.88% | 2 / 187 | 1.07% |
| `no_complete_player_pair` | 0 / 113 | 0.00% | 0 / 187 | 0.00% |
| `skipped_stride` | 0 / 113 | 0.00% | 0 / 187 | 0.00% |
| **Total** | **113 / 113** | **100.00%** | **187 / 187** | **100.00%** |

`no_complete_player_pair` is included because it occurs in the full
stride-one manifest (27 frames) even though it was not sampled by either
G161 label class. `skipped_stride` is included with zero counts because this
G152b run used stride one, so no decoded frame was skipped.

## Largest killer

**`calibration_unavailable` is the largest killer of labelled rally frames:
104 / 113 = 92.04%.** It is not close to the next bucket (8 / 113 = 7.08%),
so there is no within-noise tie to report.

The adapter records its calibration status whenever no homography is returned:

```python
# domains/tennis/tracking/adapter.py:238-239
status = (calibration_status if homography is None else
          "emitted_players" if player_count else "no_complete_player_pair")
```

The exact `calibration_unavailable` condition is the final branch of
`CameraLock.resolve`: it is reached only after the earlier ready-lock and
fresh-solve branches do not return (so the lock is not ready and `fresh` is
absent):

```python
# domains/tennis/tracking/camera_lock.py:201-205
if fresh is not None:
    check = drift_from_corners(fresh, corners)
    drift = float(check.residual_px) if check.residual_px is not None else float("nan")
    return fresh, "solved", "ready", drift, check.evidence_count
return None, "unavailable", "calibration_unavailable", float("nan"), 0
```

This memo identifies that branch only. It proposes no remedy or parameter
change.

## Evenly spaced render check

The 104-frame largest-bucket decision set was sorted by source frame. Positions
0, 26, 52, 77, and 103 yield frames 56, 5,810, 15,017, 22,019, and 28,733:

| Bucket position / frame | Render | Eye observation |
|---|---|---|
| 0 / 56 | [render](g175_stages/frame_00056_rally_calibration_unavailable.jpg) | Elevated full-court broadcast view; both court halves and the players at opposite ends are visible. |
| 26 / 5,810 | [render](g175_stages/frame_05810_rally_calibration_unavailable.jpg) | Elevated wide court view with the full playing surface, net, and both ends visible. |
| 52 / 15,017 | [render](g175_stages/frame_15017_rally_calibration_unavailable.jpg) | Tight single-player close-up; it visibly conflicts with this frame's committed `RALLY_VIEW` label. It was not re-labelled. |
| 77 / 22,019 | [render](g175_stages/frame_22019_rally_calibration_unavailable.jpg) | Elevated full-court view with net and both player halves visible. |
| 103 / 28,733 | [render](g175_stages/frame_28733_rally_calibration_unavailable.jpg) | Elevated wide view of the entire court with players at opposite ends. |

The four new renders were extracted in one batched, nice-15 `nohup` OpenCV
sequential decode on the pod from the 2 GB labelled encode; no daemon or keeper
was killed, restarted, or deployed over. The five source indices above are
evenly distributed over the largest bucket, not a head slice.

## Label-agreement limit

G161's 49/50 = 0.980 is **self-agreement by one rater**, not an independent
validity measurement. It says nothing about label validity. The frame-15,017
observation illustrates why this distinction matters. Every share in this memo
inherits that limitation; the existing labels were neither changed nor
re-labelled.

## Reproduction and contract self-check

- **A2:** Independently read the preserved 28,773-row manifest and committed
  300-row labels, keyed the manifest by `frame`, confirmed 300 unique joined
  labels and zero missing manifest rows, then recomputed the table above.
- **A3 / B7:** Render positions span 0%, 25%, 50%, 75%, and 100% of the
  104-frame winning bucket; no head slice was used.
- **A7:** Before commit, this memo, the preserved joined-source manifest, and
  all five linked renders were confirmed to exist.
- **B1:** Clear. The denominator is all 113 committed `RALLY_VIEW` labels;
  no status bucket was excluded. The 187 `NOT_RALLY` frames remain separate.
- **B2:** Clear. No schema, status value, field, reader, or alias changed.
- **B3:** Clear. A missing join would be explicit; there were zero missing
  manifest rows, and missingness was not called a failure status.
- **B4:** Clear. No claim, queue, retry, or ownership path changed.
- **B5:** Clear. No code or deployment was copied to the pod before this
  evidence; the pod work only read the existing 2 GB video to extract renders.
- **B6:** Clear. No module, import, test, or command was moved or retired.
- **B8:** Clear. This is a direct labelled-frame/status join, not a fitted
  residual or independent-label claim.
- **B9:** Clear. The unit is each unique labelled source frame, not an emitted
  row or track id.
- **B10:** Clear. No threshold, gate, bar, coordinate contract, or verdict
  was changed; the coverage-bar adjudication was not revisited.

## NOT VERIFIED

- Label validity or inter-rater agreement. G161 provides only same-rater
  repeat agreement, and the 15,017 render is not a relabelling pass.
- Byte-level equivalence of the 38 MB G152b encode and the 2 GB G161 encode.
  The join relies only on their stated common 28,773-frame decoded index span.
- Any remedy, classifier, threshold adjustment, coverage-bar adjustment, or
  downstream quality conclusion.
- No code was added, so no per-file test applied. No full pytest run was made.
