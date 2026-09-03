# G195 OpenCV RNG Route Determinism

Contract: [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md). Measurement only: no
production file was edited or deployed. The wrapper existed only in each
measurement process; nothing was copied into the pod checkout.

## Verdict: OpenCV seeding is not sufficient for route determinism

All four arms are **not identical** across their three fresh-process runs.
In particular, D (cuDNN benchmark off plus fixed OpenCV seed) emitted 1,118,
1,108, and 1,072 player rows, with differing survivor tuples at both required
source frames. OpenCV's global RNG is therefore **not sufficient to explain
the residual route variance**. It remains unverified whether it contributes a
component of that variance.

Seeding changes the output regime rather than changing nothing: seeded C/D
runs differ from unseeded A/B, but C and D still vary within arm. No extra
control was added to chase agreement.

## Fixed input, machine, and code identity

| Field | Value |
|---|---|
| Machine | Pod `5a20910184ad`; NVIDIA GeForce RTX 3090, 24,576 MiB |
| Input | `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4` |
| Input identity | 2,931,985,407 bytes; 1920x1080; 174,430 frames |
| Route arguments | `--frames 1200 --no-show --skip-features` |
| C/D OpenCV seed | `1952026` |
| `unified_pipeline.py` SHA-256 | `047dd04e9b12b588c560f68dbab32aa1855f791c2e1a46f19f4e082f50c4f331` |
| `advanced_tracker.py` SHA-256 | `df2ae698ae03e804f67639434d8303638aea9087c3169c016af5a3734dd474d7` |
| `color_reid.py` SHA-256 | `ca8e23e66ebc3ab5629870448c4cfb261039c3bec51920e54833614cbb44950f` |
| `rectify_court.py` SHA-256 | `496b264702631b18d92d48f4597bc8261fcfa6975f941b9c711d2e9de4734d5f` |

S2 premise re-check passed on the pod: `color_reid.py` has
`np.random.default_rng(0)` at 73 and one-attempt
`cv2.kmeans(..., cv2.KMEANS_PP_CENTERS)` at 77; `jersey_ocr.py` has
`KMeans(..., random_state=0)` at 382. The five RANSAC calls are
`rectify_court.py` 56/90, `video_handler.py` 145, and
`unified_pipeline.py` 1228/1299. A whole-pod `src/**/*.py` scan found no
existing `setRNGSeed` call.

## Method

Every counted run was a new pod Python process, run serially and exiting 0.
The in-memory wrapper saved `UnifiedPipeline.__init__`, called the original,
then set the arm's cuDNN benchmark setting and, for C/D only,
`cv2.setRNGSeed(1952026)`. It invoked unchanged `scripts/run_clip.py` through
`runpy` with the fixed arguments above.

| Arm | cuDNN benchmark after initializer | OpenCV seed after initializer |
|---|---|---|
| A control | on | no |
| B | off | no |
| C | on | `1952026` |
| D | off | `1952026` |

`ELIGIBLE denominator: attempted gameplay frames` is the distinct `frame`
count in that run's complete `ball_tracking.csv`, not `--frames`. Player-row
frames are distinct `tracking_data.csv` frame values. No row was filtered.
Each survivor list is all player rows at the required source frame, ordered by
player ID, team, and box.

## Per-run records (B13/Q9)

| Arm/run | Player rows | Distinct player-row frames | ELIGIBLE denominator: attempted gameplay frames | Frame 474 survivors | Frame 1377 survivors |
|---|---:|---:|---:|---|---|
| A1 | 1,510 | 400 | 400 | `(1,green,272.1164,-93.992004,408.80084,132.64157)`; `(5,green,1296.0,378.0,1434.0,609.0)`; `(9,white,1719.0,135.0,1869.0,364.0)` | `(1,green,717.0,304.0,840.0,550.0)`; `(5,green,497.45673,310.96378,617.1867,566.235)`; `(7,white,355.0,771.0,518.0,930.0)`; `(10,white,612.0,142.0,707.0,356.0)` |
| A2 | 1,311 | 400 | 400 | `(5,green,994.0,388.0,1138.0,631.0)`; `(8,white,1633.0,769.0,1753.0,928.0)` | `(2,green,256.0,744.0,391.0,921.0)`; `(3,green,717.0,304.0,840.0,550.0)`; `(9,white,165.0,792.0,323.0,930.0)`; `(10,white,659.0,478.0,812.0,770.0)` |
| A3 | 1,397 | 400 | 400 | `(5,green,1447.0,366.0,1569.0,649.0)`; `(7,white,156.78357,550.34766,264.16107,764.7256)`; `(10,white,1515.0,99.0,1611.0,298.0)` | `(4,green,165.0,792.0,323.0,930.0)`; `(5,green,28.0,803.0,180.0,927.0)`; `(6,white,355.0,771.0,518.0,930.0)`; `(10,white,487.0,264.0,584.0,538.0)` |
| B1 | 1,331 | 400 | 400 | `(3,green,1296.0,378.0,1434.0,609.0)`; `(9,white,1633.0,769.0,1753.0,928.0)` | `(3,green,582.0,655.0,750.0,822.0)`; `(4,green,256.0,744.0,391.0,921.0)`; `(5,green,717.0,304.0,840.0,550.0)`; `(7,white,1500.0,361.0,1623.0,607.0)` |
| B2 | 1,467 | 400 | 400 | `(5,green,706.0,652.0,855.0,819.0)`; `(10,white,1515.0,99.0,1611.0,298.0)` | `(3,green,717.0,304.0,840.0,550.0)`; `(4,green,256.0,744.0,391.0,921.0)`; `(5,green,582.0,655.0,750.0,822.0)`; `(8,white,487.0,264.0,584.0,538.0)`; `(9,white,659.0,478.0,812.0,770.0)`; `(10,white,356.0,771.0,518.0,930.0)` |
| B3 | 1,385 | 400 | 400 | `(5,green,1296.0,378.0,1434.0,609.0)`; `(6,white,1719.0,135.0,1869.0,364.0)` | `(2,green,256.0,744.0,391.0,921.0)`; `(5,green,717.0,304.0,840.0,550.0)`; `(8,white,659.0,478.0,812.0,770.0)`; `(9,white,356.0,771.0,518.0,930.0)`; `(10,white,907.97046,-1098.3313,1032.5492,-885.63916)` |
| C1 | 1,115 | 394 | 400 | `(4,green,527.05554,172.55698,647.937,406.79886)`; `(6,white,80.0,628.0,228.0,886.0)` | `(3,green,451.8107,67.68881,544.90375,290.58545)`; `(8,white,483.0,62.0,576.0,284.0)`; `(9,white,350.9871,122.88529,488.33664,342.5256)`; `(10,white,487.0,264.0,584.0,538.0)` |
| C2 | 933 | 390 | 400 | `(3,green,527.05554,172.55698,647.937,406.79886)`; `(6,white,80.0,628.0,228.0,886.0)` | `(1,green,463.0,72.0,556.0,297.0)`; `(7,white,483.0,62.0,576.0,284.0)`; `(8,white,352.05487,124.05042,490.04077,344.27057)` |
| C3 | 1,320 | 394 | 400 | `(2,green,522.0,149.0,641.0,384.0)`; `(5,green,174.0,286.0,376.0,532.0)`; `(7,white,80.0,628.0,228.0,886.0)` | `(2,green,256.0,744.0,391.0,921.0)`; `(3,green,511.0,292.0,625.0,552.0)`; `(5,green,563.89935,285.291,691.10944,544.07983)`; `(7,white,355.0,771.0,518.0,930.0)`; `(8,white,721.0,492.0,915.0,782.0)`; `(9,white,871.65625,458.3961,1028.3622,666.16077)` |
| D1 | 1,118 | 394 | 400 | `(3,green,527.05554,172.55827,647.937,406.80127)`; `(6,white,80.0,628.0,228.0,886.0)` | `(3,green,451.8107,67.68881,544.90375,290.58545)`; `(8,white,483.0,62.0,576.0,284.0)`; `(9,white,487.0,264.0,584.0,538.0)`; `(10,white,350.9871,122.951454,488.33664,342.33716)` |
| D2 | 1,108 | 394 | 400 | `(5,green,436.266,255.54251,582.73395,523.67957)`; `(6,white,80.0,628.0,228.0,886.0)` | `(1,green,451.8107,67.68881,544.90375,290.58545)`; `(7,white,487.0,264.0,584.0,538.0)`; `(8,white,483.0,62.0,576.0,284.0)`; `(10,white,612.0,142.0,707.0,356.0)` |
| D3 | 1,072 | 392 | 400 | `(5,green,527.05554,172.55827,647.937,406.80127)`; `(9,white,80.0,628.0,228.0,886.0)` | `(2,green,451.8107,67.68881,544.90375,290.58545)`; `(6,white,483.0,62.0,576.0,284.0)`; `(8,white,365.839,126.63545,503.04517,346.0241)`; `(9,white,612.0,142.0,707.0,356.0)` |

## Per-arm identity verdict

The local comparator included all required records above and SHA-256 hashes of
both complete emitted CSVs, excluding only the per-run directory name.

| Arm | Complete CSV hashes equal across runs? | Identical across the three runs? |
|---|---|---|
| A | no | **No** |
| B | no | **No** |
| C | no | **No** |
| D | no (`ball_tracking.csv` matched in D2/D3 only; full records still differ) | **No** |

## Focused harness test

```text
python -m pytest scripts/platformkit/tracking/test_g195_cv2_rng_route_determinism.py -q
2 passed in 0.59s
```

## VERIFIER_CONTRACT self-check

- **A2/B1:** Every emitted player/ball CSV row was recounted without filtering;
  the named eligible denominator is distinct ball-table frames.
- **A7/A9/A11:** This memo names its evidence path, exact input identity, and
  all four exercised route-file hashes.
- **B2-B6:** No schema, reader, queue, daemon, keeper, or production module
  changed. The two new local files are an evidence-only extractor and test.
- **B5:** Wrapper and extractor were streamed into process memory; no pod
  checkout file was copied or deployed.
- **B7-B10:** The two frames are pre-specified acceptance frames, not a
  quality sample. No threshold, confidence, image size, crop, coordinate
  contract, precision mode, torch seed, corpus, daemon, or keeper changed.

## NOT VERIFIED

- Whether OpenCV's global RNG contributes any component of residual variance;
  it is not sufficient alone, but it is not proved irrelevant.
- The remaining causal source(s), any quality/calibration conclusion, and any
  conclusion beyond this one video with `n = 3` per arm.
- The initial seed `19520260903` is not a run record: OpenCV rejected it as
  outside its C-int range before route output. The twelve counted jobs used
  valid seed `1952026` in C/D and exited 0.
