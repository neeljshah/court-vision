# Soccer S1 stream packet -- 2026-09-02

## Scope

G08 measures tracker churn on the three clips used by the sealed soccer S1
packet. It is a stream-only diagnostic: it does not change a threshold and it
does not re-adjudicate S1 or alter its AMBIGUOUS verdict.

Each clip contributes five seeded, timeline-stratified, sequential 10-second
windows. Frames were decoded sequentially with OpenCV; every window uses one
fresh `SoccerAdapter` instance so its image-space tracker carries state through
that window. The pod did not yet carry G22's helper, so the unchanged merged
`scripts.platformkit.detection.deterministic` helper was copied before the
run. It fixes Python, NumPy, Torch, and OpenCV controls before the detector is
loaded. The pod used seed 20260902.

`mean_raw_person_boxes_per_frame` is the adapter's valid person detection
count. `id_churn_ratio = (new IDs / decoded frames) / mean boxes`, equivalently
the sum of window-distinct IDs divided by all person detections. Homography
was attempted every 10 frames, so each 300-frame window has 30 attempts;
`homography_lock_rate` is accepted attempts divided by attempts.

## Per-window measurements

| clip | window | start frame | decoded | mean boxes | distinct IDs | churn | frames >=14 | H lock |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| soccer_AgspyOj5BPk | 1 | 721 | 300 | 10.34 | 24 | 0.00774 | 0.447 | 0/30 |
| soccer_AgspyOj5BPk | 2 | 10962 | 300 | 10.53 | 38 | 0.01203 | 0.370 | 0/30 |
| soccer_AgspyOj5BPk | 3 | 13780 | 300 | 11.09 | 33 | 0.00992 | 0.507 | 0/30 |
| soccer_AgspyOj5BPk | 4 | 20669 | 300 | 14.95 | 29 | 0.00647 | 0.690 | 0/30 |
| soccer_AgspyOj5BPk | 5 | 25062 | 300 | 13.77 | 31 | 0.00750 | 0.477 | 0/30 |
| soccer_DdnvC6-PGYY | 1 | 725 | 300 | 9.70 | 27 | 0.00928 | 0.083 | 0/30 |
| soccer_DdnvC6-PGYY | 2 | 11018 | 300 | 8.29 | 17 | 0.00683 | 0.007 | 0/30 |
| soccer_DdnvC6-PGYY | 3 | 13851 | 300 | 10.50 | 25 | 0.00794 | 0.303 | 0/30 |
| soccer_DdnvC6-PGYY | 4 | 20775 | 300 | 7.68 | 38 | 0.01649 | 0.233 | 0/30 |
| soccer_DdnvC6-PGYY | 5 | 25190 | 300 | 17.16 | 26 | 0.00505 | 0.887 | 0/30 |
| soccer_kSgNjoaqCpI_1080p | 1 | 451 | 300 | 10.72 | 32 | 0.00995 | 0.270 | 0/30 |
| soccer_kSgNjoaqCpI_1080p | 2 | 6864 | 300 | 12.46 | 27 | 0.00723 | 0.487 | 0/30 |
| soccer_kSgNjoaqCpI_1080p | 3 | 8629 | 300 | 9.74 | 20 | 0.00685 | 0.297 | 0/30 |
| soccer_kSgNjoaqCpI_1080p | 4 | 12943 | 300 | 14.75 | 21 | 0.00475 | 0.663 | 0/30 |
| soccer_kSgNjoaqCpI_1080p | 5 | 15694 | 300 | 17.07 | 29 | 0.00566 | 0.890 | 0/30 |

## Per-clip summary

| clip | frames | mean boxes | new IDs | churn | frames >=14 | H lock |
|---|---:|---:|---:|---:|---:|---:|
| soccer_AgspyOj5BPk | 1500 | 12.14 | 155 | 0.00852 | 0.498 | 0/150 |
| soccer_DdnvC6-PGYY | 1500 | 10.67 | 133 | 0.00831 | 0.303 | 0/150 |
| soccer_kSgNjoaqCpI_1080p | 1500 | 12.95 | 129 | 0.00664 | 0.521 | 0/150 |
| pooled | 4500 | 11.92 | 417 | 0.00778 | 0.441 | 0/450 |

All 450 calibration attempts failed. Thus this run measures image-space
tracker churn only; it does not establish court-coordinate tracking quality.

## Render-and-look tally

Two endpoint renders were reviewed for each window (30 total):

| clip | apparent persistent IDs | apparent changed IDs | unassessable endpoint pairs |
|---|---:|---:|---:|
| soccer_AgspyOj5BPk | 0 | 0 | 5 |
| soccer_DdnvC6-PGYY | 1 | 1 | 3 |
| soccer_kSgNjoaqCpI_1080p | 0 | 0 | 5 |
| total | 1 | 1 | 13 |

Endpoint renders are too sparse to estimate an identity-persistence rate:
most pairs include a broadcast cut, close-up, replay angle, or insufficient
same-subject detail. The one apparent changed label is a readily identifiable
goalkeeper in DdnvC6-PGYY window 3. This limited visual result is consistent
with the numeric churn measurement being an instrument for a future prereg,
not a decision rule for DETECTOR-BOUND versus CAMERA-BOUND.

## Artifacts and integrity

- `g08_soccer_AgspyOj5BPk/soccer_s1_stream_windows.csv` SHA-256:
  `18baf2166c6538015a47234fbae863dc7c7d4d9c048b51ba0d0012230642aa3d`
- `g08_soccer_DdnvC6-PGYY/soccer_s1_stream_windows.csv` SHA-256:
  `ab1e9a9082c04042b565e721b2797e5f7319c3508cced36088ea41087700a513`
- `g08_soccer_kSgNjoaqCpI_1080p/soccer_s1_stream_windows.csv` SHA-256:
  `68a2867cabcf1253af4e0efe0242e6aa2addffc3734d468471dc4ade4ea1dab3`

Each directory also includes its seed/selection manifest and ten annotated
endpoint renders. Local verification: `python -m pytest
scripts/platformkit/test_soccer_s1_stream_packet.py -q` reported `1 passed`.
