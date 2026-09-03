# G166: tennis epoch-churn attribution

Contract: [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md), sections A (A2, A3,
A7), B, and Q8. This is a pod-only, temporary-instrumentation measurement.
No adapter, identity, camera-lock, threshold, bar, coordinate contract, shared
tracking table, daemon, keeper, or verdict was changed.

## Run identity and method

The run uses scratch game id `g166_epoch_probe_20260903`, source
`data/videos/tennis_smoke.mp4`, `max_frames=30000`, and the normal adapter-run
timebase stride. The preserved temporary adapter differential is committed as
[g166_epoch_churn_instrumentation.diff](g166_epoch_churn_instrumentation.diff).
It was copied only to `/workspace/g166_epoch_probe_20260903/adapter.py` and
loaded by that isolated process; the pod's live source tree was not overwritten
and no process was restarted.

The probe records every call to `_end_track_ids`, its call-site cause, its source
frame, and whether centroids existed before the call. The eligible epoch-end
denominator is the subset with centroids: only those calls advance
`_track_id_base` by two in `end_epoch`; a no-centroid call is a reset attempt,
not an identity epoch end. All call attempts are reported separately.

## Results

The run decoded all **28,773** frames and emitted **1,861** rows at stride 3.
The raw exhaustive artifact is [g166_epochs/result.json](g166_epochs/result.json).

### Q8 premise remeasurement and attribution

The stated premise is confirmed, not assumed: there are **293 eligible epoch
ends** and final id base **586**, exactly reproducing the historical 293 epochs
implied by the 1..586 two-id allocation.

The eligible denominator is **293 actual identity epoch ends**. It excludes
calls with no centroids because `end_epoch` cannot advance the id base for them.

| Call site / cause | Actual ends | Share of 293 eligible ends | All calls | Share of 673 calls |
|---|---:|---:|---:|---:|
| `detect_cut` | 31 | 10.58% | 221 | 32.84% |
| `_reset_temporal_calibration` / `calibration_loss` | 1 | 0.34% | 148 | 21.99% |
| `emission_gap` | 261 | 89.08% | 304 | 45.17% |
| **Total** | **293** | **100.00%** | **673** | **100.00%** |

The remaining 380 calls had no centroids: 190 `detect_cut`, 147
`calibration_loss`, and 43 `emission_gap`. They are retained in the raw artifact
and not folded into the epoch denominator.

### Drift-probe distribution

The temporary probe captured **862 transformed-probe comparisons** where both
candidate and previous homographies existed. This is its eligible denominator,
not all decoded frames. Values are the maximum Euclidean displacement across the
three transformed probes, in homography output-coordinate units.

| n | Min | P25 | Median | P75 | P90 | P95 | Max | Greater than unchanged 8.0 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 862 | 0.112 | 2.346 | 4.892 | 11.526 | 26.806 | 47.826 | 57.959 | 279 / 862 = 32.37% |

This is broad and high-tailed, but it does **not** establish the 279 crossings
as the 1 eligible calibration-loss epoch. In the measured adapter, an
`_in_tolerance` failure marks the current calibration unavailable and returns;
the `calibration_loss` reset call is the prolonged no-corner /
camera-lock-not-ready path. The 8.0 threshold remains exactly unchanged.

## Required eye check

The selection is committed in [g166_epochs/selection.json](g166_epochs/selection.json).
For decoded-frame targets `round(i * (28773 - 1) / 4)`, i=0..4, it selects the
nearest eligible epoch boundary. The selected sources span 617 through 28,467,
not a head slice.

| Target / selected boundary | Cause | Render | Eye verdict |
|---|---|---|---|
| 0 / 616 -> 617 | `detect_cut` | [pair 01](g166_epochs/pair_01.png) | Genuine shot cut: wide court to player close-up. |
| 7,193 / 7,463 -> 7,464 | `emission_gap` | [pair 02](g166_epochs/pair_02.png) | Same continuous wide-court rally and same two players; false identity reset. |
| 14,386 / 14,444 -> 14,445 | `emission_gap` | [pair 03](g166_epochs/pair_03.png) | Same continuous wide-court rally and same two players; false identity reset. |
| 21,579 / 21,569 -> 21,570 | `emission_gap` | [pair 04](g166_epochs/pair_04.png) | Same continuous wide-court rally and same two players; false identity reset. |
| 28,772 / 28,466 -> 28,467 | `detect_cut` | [pair 05](g166_epochs/pair_05.png) | Genuine shot cut: wide court to player close-up. |

## Position on the unchanged median-track-length bar

`median_track_len >= 3.00` remains unchanged and was not re-scored here. This
result does **not** support CLOSED AT LIMIT on a broadcast-cut-frequency theory:
`detect_cut` contributes **31 / 293 = 10.58%** of actual ends, while
`emission_gap` contributes **261 / 293 = 89.08%**, and all three sampled
`emission_gap` boundaries are same-rally false resets. The bar is not shown
unreachable on this footage by cut frequency. No remedy, lower bar, threshold
change, or verdict change is proposed.

## Verifier self-check

- **A2:** Recomputed attribution and every drift quantile from committed raw
  `result.json`, not from the process log.
- **A3 / B7:** Five pairs use equal decoded-frame targets across all 28,773
  frames; `selection.json` records target, selected boundary, and distance.
- **A7:** The diff, raw JSON, selection JSON, and all five named PNGs exist.
- **B1:** Every call is retained; the 293 advancing calls and 380 no-op calls
  are named separately.
- **B2-B4, B6:** No production schema, reader, runtime claim path, module, or
  retry behavior changed.
- **B5:** The required temporary adapter copy was a scratch-only measurement
  input, not a deployment: it did not replace the pod source module or running
  daemon, and no restart occurred.
- **B8-B9:** No fitted or recycled metric is presented; the denominator is the
  identity-base advance observed per call.
- **B10 / Q3:** The 8.0 threshold and every other bar are unchanged.
- **Q8:** G162's premise was remeasured first and holds exactly: 293 ends,
  final base 586, 28,773 decoded frames, and 1,861 output rows.

## NOT VERIFIED

- Why each `emission_gap` occurs internally; this harness attributes call site,
  not the missing-player-emission mechanism.
- A causal mapping from any above-8.0 probe displacement to a later no-corner
  reset. This run did not add a full camera-lock trace.
- Every boundary's visual status. The required five are an even eye sample, not
  an audit of all 293.
- Any change to tracking behavior, quality gate outcome, coordinate contract,
  or production service.
