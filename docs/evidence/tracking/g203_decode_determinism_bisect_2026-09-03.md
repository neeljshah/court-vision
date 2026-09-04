# G203 Decode Determinism Bisect

Contract: [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md). Measurement only: no production module or pod-checkout file was edited or deployed. The harness was streamed into each fresh process; daemon, keeper, and corpus were untouched.

## Verdict: decode is byte-identical on the measured route

Both required parts have identical ordered per-frame SHA-256 sequences across three fresh, serial pod processes. The route therefore saw the same decoded pixels each time. Decode is eliminated as the last enumerated candidate for residual whole-route non-determinism; the remaining search is stateful logic given identical pixel inputs.

The unchanged route used PyAV in every run. The outer decord fallback handler fired once per run because the unchanged default leaves `DECORD_ENABLE` unset and intentionally falls through to PyAV. DLPack, sequential-batch, and decode-loop handlers never fired; the decoder never changed mid-run.

## Fixed input, machine, and code identity

| Field | Value |
|---|---|
| Machine | Pod `5a20910184ad`; NVIDIA GeForce RTX 3090, 24,576 MiB |
| Input | `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4` |
| Input identity | 2,931,985,407 bytes; 1920x1080; 174,430 frames |
| Route arguments | `--frames 1200 --no-show --skip-features` |
| `unified_pipeline.py` SHA-256 | `047dd04e9b12b588c560f68dbab32aa1855f791c2e1a46f19f4e082f50c4f331` |
| `advanced_tracker.py` SHA-256 | `df2ae698ae03e804f67639434d8303638aea9087c3169c016af5a3734dd474d7` |
| Match to G195 / G198? | Yes, both exactly match both prior artifacts. |

## Method

Each counted run was a fresh, serial pod process. A process-local wrapper imported the production `_decord_frame_iter` rather than reimplementing decode, hashed `frame.tobytes(order="C")`, recorded frame index and decoder, and traced only the four named handler bodies. It added no seed, precision, decoder, threshold, crop, image-size, or route-option control.

Part 1 iterated the production decoder with the fixed 1,200-source-frame bound. Its eligible denominator is the 400 delivered indices satisfying the route's unchanged stride-three gameplay pattern. Part 2 intercepted only a successful `_FramePrefetcher.read`, immediately after the tracking loop received its item. Its eligible denominator is that observed attempted-gameplay count, never `--frames`.

## Part 1: decode in isolation

| Run | Frames hashed | ELIGIBLE denominator: attempted gameplay frames | Hashes differing from run 1 | First differing frame index | Decoder changed? | Silent handlers |
|---|---:|---:|---:|---|---|---|
| I1 | 1,200 | 400 | 0 | none | No | outer fallback: 1; others: 0 |
| I2 | 1,200 | 400 | 0 | none | No | outer fallback: 1; others: 0 |
| I3 | 1,200 | 400 | 0 | none | No | outer fallback: 1; others: 0 |

**I1-I3 are identical.** All frames were PyAV; no mid-run decoder change occurred.

## Part 2: decode as the route consumes it

| Run | Frames hashed | ELIGIBLE denominator: attempted gameplay frames | Hashes differing from run 1 | First differing frame index | Decoder changed? | Silent handlers |
|---|---:|---:|---:|---|---|---|
| R1 | 461 | 461 | 0 | none | No | outer fallback: 1; others: 0 |
| R2 | 461 | 461 | 0 | none | No | outer fallback: 1; others: 0 |
| R3 | 461 | 461 | 0 | none | No | outer fallback: 1; others: 0 |

**R1-R3 are identical.** All frames were PyAV; no mid-run decoder change occurred. The Part 2 denominator is the observed successful tracking-consumer read count.

## Complete records (B13/Q9)

All six complete ordered records are committed beside this memo: [g203_decode_determinism_bisect_2026-09-03_records.json](g203_decode_determinism_bisect_2026-09-03_records.json). It includes every frame index, raw-byte hash, decoder label, handler count, and denominator. SHA-256: `aba1dcb98ad74aa133e34611b965ddf1b12ee298c814a44b1fc567b826578338`.

## Focused harness test

```text
python -m pytest scripts/platformkit/tracking/test_g203_decode_determinism_bisect.py -q
2 passed
```

## VERIFIER_CONTRACT self-check

- **A7/A9/A11/B13/Q9:** Committed evidence records fixed corpus identity, code hashes, denominators, and complete per-frame data.
- **B2-B6:** No production module, pod checkout, daemon, keeper, schema, or corpus changed.
- **B7-B10:** No seed, precision, threshold, confidence, image size, crop, coordinate contract, flag, bar, or route argument changed.
- **A12:** The 251-LOC harness is below the LOC rail; no allowlist entry changed.

## NOT VERIFIED

- The remaining stateful source(s) downstream of identical pixels.
- Other videos, GPUs, strides, route configurations, or decoder environments.
- Decord byte identity: the unchanged route selected PyAV, so G203 did not exercise decord.
- Tracking quality, calibration, or performance conclusions.
