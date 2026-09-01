# Soccer S4 coverage packet, 2026-09-01

## Verdict: S4 is falsified on this corpus

Claim tested: main-camera soccer broadcasts physically cannot satisfy the frozen
`min_players=14` requirement at `coverage_min=0.85`.  This is not true for the
measured corpus.  `soccer_AgspyOj5BPk` reaches **33** simultaneous distinct
observed players in one frame.  Fifteen native-provenance games have at least
one 14-player frame.  Therefore this is a counterexample packet, not an
impossibility packet; do not claim a camera-class ceiling from these files.

Frozen harness clause (`scripts/platformkit/tracking_harness.py`):

```python
per_frame = players.groupby("frame")["track_id"].nunique()
coverage = float((per_frame >= cfg["min_players"]).sum() / n_frames)
# soccer: min_players=14, coverage_min=0.85
```

## Reproduction

All commands were read-only on the pod; the measurement process was lowered
with `nice -n 15`.  No daemon or `data/footage_bridge` path was touched.

```text
ssh -p 40048 root@213.192.2.83 \
  "cd /workspace/nba-ai-system && nice -n 15 find data/tracking \
   -path 'data/tracking/soccer_*/tracking_data.csv' -type f -print"
```

Output: 24 CSVs, one at `data/tracking/soccer_<id>/tracking_data.csv` for each
`<id>` below.  Each was loaded with pandas and passed to
`domains.soccer.tracking.coverage_ceiling.measure(rows, min(frame), max(frame))`.
For the nine legacy five-column CSVs marked `L`, the read-only in-memory input
was `rows.assign(observation="observed")`; their source format has no inferred
row type.  The S4-killing 33-player result is native provenance-marked, so it
does not depend on that compatibility declaration.

```text
# Run once for each of the three listed batches; NAMES is the literal batch list.
ssh -p 40048 root@213.192.2.83 "cd /workspace/nba-ai-system && \
  echo <base64 of the Python below> | base64 -d | nice -n 15 python -"

for name in NAMES:
    rows = pd.read_csv(Path('data/tracking') / name / 'tracking_data.csv')
    legacy = 'observation' not in rows.columns
    if legacy:
        rows = rows.assign(observation='observed')
    report = measure(rows, int(rows['frame'].min()), int(rows['frame'].max()))
    print(name, len(rows), legacy, report)
```

Output (the `rows` and `observed rows` equality confirms the diagnostic did not
discard source detections; `frames` is `last - first + 1`, including zero-row
frames):

| Game id | L | Rows | Frame range | Frames | Observed rows | Median | P90 | Max | Frames >=14 |
|---|:---:|---:|---|---:|---:|---:|---:|---:|---:|
| -YbZsM26GDI | Y | 7,221 | 429-28,794 | 28,366 | 7,221 | 0.0 | 0.0 | 27 | 279 |
| 6dIn3fUfI6U | N | 96,168 | 0-28,608 | 28,609 | 96,168 | 0.0 | 14.0 | 25 | 3,145 |
| 7fOG8j_ncWY | N | 68,211 | 0-28,797 | 28,798 | 68,211 | 0.0 | 12.0 | 22 | 1,840 |
| 8_DRy2i5-hs | N | 75,954 | 0-28,797 | 28,798 | 75,954 | 0.0 | 13.0 | 27 | 2,789 |
| A9ad17VZvs8 | N | 6,126 | 0-28,041 | 28,042 | 6,126 | 0.0 | 0.0 | 25 | 146 |
| AgspyOj5BPk | N | 107,232 | 0-28,803 | 28,804 | 107,232 | 0.0 | 18.0 | **33** | 4,682 |
| Cn26lFZ0_jI | N | 64,359 | 648-28,647 | 28,000 | 64,359 | 0.0 | 12.0 | 25 | 2,442 |
| DdnvC6-PGYY | N | 34,728 | 0-28,950 | 28,951 | 34,728 | 0.0 | 3.0 | 28 | 979 |
| EKhrdU9bVZA | N | 90,058 | 0-28,755 | 28,756 | 90,058 | 0.0 | 15.0 | 31 | 3,522 |
| GF-WteOINCc | N | 80,980 | 255-28,797 | 28,543 | 80,980 | 0.0 | 14.0 | 28 | 2,912 |
| HkN1E3HESS8 | Y | 1,632 | 27-28,350 | 28,324 | 1,632 | 0.0 | 0.0 | 14 | 2 |
| HxBqMbI5kqQ | N | 91,744 | 0-28,737 | 28,738 | 91,744 | 0.0 | 13.0 | 28 | 2,668 |
| JIQnnYy7qYk | N | 88,867 | 0-28,797 | 28,798 | 88,867 | 0.0 | 15.0 | 24 | 3,947 |
| JLMH7eUeJBY | Y | 26,361 | 210-28,797 | 28,588 | 26,361 | 0.0 | 5.0 | 19 | 92 |
| Pbyn08kfhXY | N | 81,222 | 0-28,797 | 28,798 | 81,222 | 0.0 | 12.0 | 25 | 1,992 |
| QIpZ1pad73w | N | 110,774 | 0-28,797 | 28,798 | 110,774 | 0.0 | 17.0 | 24 | 5,542 |
| Z6NTDyxcODs | Y | 29,785 | 198-28,797 | 28,600 | 29,785 | 0.0 | 5.0 | 15 | 5 |
| c1mzmBGHQr4 | Y | 523 | 2,007-28,782 | 26,776 | 523 | 0.0 | 0.0 | 6 | 0 |
| cKXZysISV4w | N | 98,261 | 0-28,950 | 28,951 | 98,261 | 0.0 | 15.0 | 27 | 3,625 |
| ci4vyd6PsNg | N | 102,639 | 300-28,797 | 28,498 | 102,639 | 0.0 | 15.0 | 29 | 4,297 |
| dnR5C6WLJI4 | Y | 4,111 | 339-28,797 | 28,459 | 4,111 | 0.0 | 0.0 | 11 | 0 |
| kSgNjoaqCpI | Y | 5,025 | 204-28,800 | 28,597 | 5,025 | 0.0 | 0.0 | 10 | 0 |
| lv2CukQcR5s | Y | 40,624 | 93-28,713 | 28,621 | 40,624 | 0.0 | 7.0 | 22 | 601 |
| y0-6FHIaiZA | Y | 11,710 | 402-28,797 | 28,396 | 11,710 | 0.0 | 0.0 | 21 | 240 |

## Scope retained

The immutable harness remains untouched.  Consumers may use this declared
`image_px` corpus as image-space / visual teacher data.  It is not court- or
pitch-coordinate harness evidence without a valid transform.  This result does
not say soccer tracking is impossible; it rejects only the proposed claim that
this main-camera class can never attain 14 visible players.  The visible-player
corpus remains valid teacher data.
