# G231 tennis out-of-bounds structure diagnosis

## Scope and inputs

S1 machine: this analysis ran locally in `C:\Users\neelj\nba-track-a5`. It did not use the pod, network, source video, production route, `src/`, or `domains/` imports. The inputs are committed CSV tables, so raster resolution is not applicable. Source width is not recorded in any table.

| Table | Full local input path | Bytes | Rows | SHA-256 | coordinate space | Source fps | Source height |
|---|---|---:|---:|---|---|---:|---:|
| `tennis_ref01` | `C:\Users\neelj\nba-track-a5\docs\evidence\tracking\g219_inputs\tennis_ref01_tracking_data.csv` | 252850 | 1861 | `77accc8cd83dee040601605a19bd7db592a703b2dd2bdf066fb0f2a8245f567b` | `court_feet` only | 29.97 | 360 |
| `tennis_01` | `C:\Users\neelj\nba-track-a5\docs\evidence\tracking\g219b_inputs\tennis_01_tracking_data.csv` | 2832341 | 19437 | `4e0def5dd2a53570d3aba4c5893f9761a8d695e62c16da5d0b60b12ab87c3929` | `court_feet` only | 59.94005994005994 | 1080 |
| `tennis_02` | `C:\Users\neelj\nba-track-a5\docs\evidence\tracking\g219b_inputs\tennis_02_tracking_data.csv` | 255168 | 1637 | `a2f8147401f85044fa8d0a120d1bf316a497db959b845b520eaad5a58dc2d2cd` | `court_feet` only | 59.94005994005994 | 1080 |

All three SHA-256 values, row counts, and `court_feet` declarations match G230. The eligible denominator is explicitly `cls == player`, not all rows, because historical ball IDs collide with player epochs.

| Table | Eligible player rows | Ball rows | All rows |
|---|---:|---:|---:|
| `tennis_ref01` | 1430 | 431 | 1861 |
| `tennis_01` | 16766 | 2671 | 19437 |
| `tennis_02` | 1504 | 133 | 1637 |

The complete, unrounded analysis is [`g231_out_of_bounds_structure_2026-09-04.json`](g231_out_of_bounds_structure_2026-09-04.json). It stores all per-track and per-source-frame numerators and denominators, rather than a sampled slice.

## Direction: the primary diagnostic

Every out-of-bounds player row is classified by every exceeded edge of the adapter's declared 78 by 36 foot plane. A row at a corner appears once in the joint distribution and once for each applicable marginal edge.

| Table | OOB player rows | Joint distribution: count |
|---|---:|---|
| `tennis_ref01` | 196 | `x_lt_0`: 148; `x_gt_78`: 2; `x_gt_78 + y_gt_36`: 6; `x_gt_78 + y_lt_0`: 26; `y_gt_36`: 6; `y_lt_0`: 8 |
| `tennis_01` | 12805 | `x_lt_0`: 6425; `x_gt_78`: 4154; `x_gt_78 + y_gt_36`: 402; `x_gt_78 + y_lt_0`: 880; `x_lt_0 + y_gt_36`: 23; `x_lt_0 + y_lt_0`: 20; `y_gt_36`: 459; `y_lt_0`: 442 |
| `tennis_02` | 1140 | `x_lt_0`: 571; `x_gt_78`: 428; `x_gt_78 + y_gt_36`: 6; `x_gt_78 + y_lt_0`: 87; `y_gt_36`: 4; `y_lt_0`: 44 |

| Table | `x_lt_0` | `x_gt_78` | `y_lt_0` | `y_gt_36` |
|---|---:|---:|---:|---:|
| `tennis_ref01` | 148 | 34 | 34 | 12 |
| `tennis_01` | 6468 | 5436 | 1342 | 884 |
| `tennis_02` | 571 | 521 | 131 | 10 |

Observed pattern: this is **structured**, not a spread across all four edges. `tennis_ref01` is predominantly beyond one edge, `x < 0` (148 of 196 OOB rows). The two G219b tables are primarily beyond **both ends of the x axis**: 11904 of 12805 (`tennis_01`) and 1092 of 1140 (`tennis_02`) OOB rows exceed an x edge. Under the pre-registered taxonomy, that is an x-axis scale/extent signature, not a one-edge translation signature and not unstructured noise.

That signature does not establish a unique upstream cause. The negative-side mass prevents a single positive origin scale from bringing the bulk fully inside, as shown next.

## Explicit scale test

For each table, the diagnostic divides both coordinates by positive `k` and minimizes the player OOB count. The objective is monotone: increasing `k` moves positive coordinates inward while negative coordinates remain negative. The reported `k` is therefore the smallest boundary-ratio value attaining the minimum, not an independent fitted-model validation.

| Table | Baseline OOB | Smallest minimizing `k` | Residual OOB rows | Residual fraction |
|---|---:|---:|---:|---:|
| `tennis_ref01` | 196 / 1430 | 1.297132 | 182 / 1430 | 12.7273% |
| `tennis_01` | 12805 / 16766 | 1.579292 | 7790 / 16766 | 46.4631% |
| `tennis_02` | 1140 / 1504 | 1.479525 | 702 / 1504 | 46.6755% |

At each minimizing `k`, the remaining OOB rows are precisely rows with a negative x or y coordinate: 182 in `tennis_ref01`, 7790 in `tennis_01`, and 702 in `tennis_02`. Thus a uniform positive scale can remove positive-side exceedances but cannot explain the two high-OOB tables as a complete single-scale error.

The singles/doubles ratio `36 / 27 = 1.333` is not the result for either high-OOB table (1.579292 and 1.479525). More basically, using a doubles model for a singles court makes the reference plane larger, so that mix-up alone cannot push positions out of its bounds. The numbers do not support that explanation.

## Per-track and source-frame distributions

All individual track and source-frame results are in the JSON artifact. The summaries below distinguish a small number of bad identities from broad table behavior.

| Table | Tracks | Clean tracks | All-OOB tracks | Mixed tracks | Track OOB fraction p10 / median / p90 |
|---|---:|---:|---:|---:|---|
| `tennis_ref01` | 586 | 486 | 81 | 19 | 0.0000 / 0.0000 / 1.0000 |
| `tennis_01` | 536 | 60 | 309 | 167 | 0.0000 / 1.0000 / 1.0000 |
| `tennis_02` | 414 | 122 | 280 | 12 | 0.0000 / 1.0000 / 1.0000 |

`tennis_01` has 476 non-clean tracks of 536, and `tennis_02` has 292 of 414. Their high OOB rates are therefore not attributable to a handful of fully off-court tracks. In contrast, `tennis_ref01` confines OOB rows to 100 of 586 tracks, consistent with its far lower table-level rate but not proving an identity cause.

| Table | Emitted source frames | Clean frames | All-OOB frames | Mixed frames | Per-frame OOB fraction p10 / median / p90 |
|---|---:|---:|---:|---:|---|
| `tennis_ref01` | 715 | 533 | 14 | 168 | 0.0000 / 0.0000 / 0.5000 |
| `tennis_01` | 8383 | 291 | 4713 | 3379 | 0.5000 / 1.0000 / 1.0000 |
| `tennis_02` | 752 | 41 | 429 | 282 | 0.5000 / 1.0000 / 1.0000 |

For a compact time view, the following are OOB fractions in ten equal source-frame spans, earliest to latest. Exact results for every emitted source frame, including their named denominators, are in the JSON artifact.

| Table | Ten chronological source-frame-span OOB fractions |
|---|---|
| `tennis_ref01` | 0.2297, 0.0707, 0.1313, 0.1562, 0.1491, 0.0645, 0.1524, 0.1250, 0.0714, 0.2089 |
| `tennis_01` | 0.7921, 0.7953, 0.7995, 0.7672, 0.7799, 0.7713, 0.7621, 0.7435, 0.7564, 0.6388 |
| `tennis_02` | 0.7600, 0.8209, 0.7778, 0.7000, 0.7955, 0.8034, 0.7308, 0.6903, 0.6667, 0.8130 |

Neither high-OOB table exhibits a single contiguous high-OOB interval in this exhaustive temporal view: both remain high across all ten source-frame spans. The reference table remains lower but nonzero across its full time range. This does not support diagnosing one temporally localized failed re-solve from these tables.

## Calibration provenance and projection status

| Table | `calibration_provenance` | Eligible player rows | OOB rows | OOB fraction |
|---|---|---:|---:|---:|
| `tennis_ref01` | `solved` | 1200 | 168 | 14.0000% |
| `tennis_ref01` | `camera_lock_drift_checked` | 230 | 28 | 12.1739% |
| `tennis_01` | `solved` | 7186 | 5501 | 76.5516% |
| `tennis_01` | `camera_lock_drift_checked` | 9580 | 7304 | 76.2422% |
| `tennis_02` | `solved` | 442 | 309 | 69.9095% |
| `tennis_02` | `camera_lock_drift_checked` | 1062 | 831 | 78.2486% |

For eligible player rows, `projection_status` has only one distinct value in every table: `(blank)`. Its requested breakdown is therefore the table total: `tennis_ref01` 196 / 1430 (13.7063%), `tennis_01` 12805 / 16766 (76.3748%), and `tennis_02` 1140 / 1504 (75.7979%). It cannot discriminate a cause here. The joint provenance/status table is identical to the provenance table because status is blank.

`tennis_01` is almost identical across provenance labels (76.55% solved, 76.24% drift-checked). `tennis_02` differs by 8.34 percentage points, but three historical tables without image evidence or a controlled comparison cannot attribute that association to camera-lock reuse. The source defines its relevant reuse guard at `domains/tennis/tracking/camera_lock.py:13-14` and applies its fresh-solve and drift checks at `domains/tennis/tracking/camera_lock.py:176-181`; the retained tables do not contain the residuals needed to diagnose that code as the cause.

## Diagnosis, limitations, and self-check

Diagnosis: G231 establishes a structured, persistent x-axis out-of-bounds pattern in `tennis_01` and `tennis_02`, with mass beyond both x ends across many tracks and throughout their source-frame ranges. It rejects a complete uniform-positive-scale explanation because the fitted rescaling leaves 46.46% and 46.68% OOB, respectively, all on negative coordinate sides. It does **not** establish a specific implementation or camera-lock cause. `tennis_ref01` has a lower, mostly one-edge `x < 0` pattern and therefore does not share the same table-level shape.

No gate, threshold, bar, coordinate-contract, `src/`, `domains/`, input, pod, or deployment change was introduced, moved, proposed, or applied.

Reproduction, locally only:

```text
python scripts/platformkit/tracking/g231_out_of_bounds_structure.py docs/evidence/tracking/g219_inputs/tennis_ref01_tracking_data.csv docs/evidence/tracking/g219b_inputs/tennis_01_tracking_data.csv docs/evidence/tracking/g219b_inputs/tennis_02_tracking_data.csv --output docs/evidence/tracking/g231_out_of_bounds_structure_2026-09-04.json
python -m pytest scripts/platformkit/tracking/test_g231_out_of_bounds_structure.py -q
```

Focused test result: `1 passed`.

Contract self-check: B1 uses every `cls == player` row and names ball exclusions; B2-B4 change no schema, status, or claim lifecycle; B5 made no pod deployment; B6 moves no module; B7 has no renders because this is exhaustive table analysis; B8 labels the requested same-data scale residual as descriptive rather than independent validation; B9 uses actual player rows, track IDs, and source frames with named denominators; B10 changes no bar or gate. A7: this memo and the JSON artifact named above exist before commit. A12 does not apply: the new PlatformKit analyzer is 223 lines and no allowlisted file changed.

NOT VERIFIED: source-video ground truth; source width; singles versus doubles for each clip; any coordinate's correctness merely because it is inside the plane; the historical non-deterministic route's repeatability; the per-frame image residuals or corner evidence necessary to identify a camera-lock or specific homography cause; and the reason for unobserved no-emission intervals.
