# G230 tennis physical-plausibility audit

## Verdict: ACCEPT (descriptive measurement only)

This is a local-only, exhaustive audit of three committed tennis tracking tables. It introduces **no gate and no threshold**. Every physical reference below describes a distribution; it does not pass or fail any row. The evidence follows `docs/evidence/tracking/VERIFIER_CONTRACT.md` sections A and B.

## Inputs and premise check

S1 machine: analysis ran locally in `C:\Users\neelj\nba-track-a4`; no pod, network, route, source video, or production code was used. Each opened input is tabular CSV, so raster resolution is not applicable.

| Table | Full local path | Bytes | Rows | SHA-256 | coordinate_space |
|---|---|---:|---:|---|---|
| `tennis_ref01` | `C:\Users\neelj\nba-track-a4\docs\evidence\tracking\g219_inputs\tennis_ref01_tracking_data.csv` | 252850 | 1861 | `77accc8cd83dee040601605a19bd7db592a703b2dd2bdf066fb0f2a8245f567b` | `court_feet` only |
| `tennis_01` | `C:\Users\neelj\nba-track-a4\docs\evidence\tracking\g219b_inputs\tennis_01_tracking_data.csv` | 2832341 | 19437 | `4e0def5dd2a53570d3aba4c5893f9761a8d695e62c16da5d0b60b12ab87c3929` | `court_feet` only |
| `tennis_02` | `C:\Users\neelj\nba-track-a4\docs\evidence\tracking\g219b_inputs\tennis_02_tracking_data.csv` | 255168 | 1637 | `a2f8147401f85044fa8d0a120d1bf316a497db959b845b520eaad5a58dc2d2cd` | `court_feet` only |

All prescribed hashes and counts match. The declared plane is 78 by 36 feet, read from the local source `C:\Users\neelj\nba-track-a4\domains\tennis\tracking\adapter.py` (16970 bytes, SHA-256 `f7687c5646dfa3f9a8206d1559238941020b6f5828d28c160e11426699a2bac9`; source text, raster resolution not applicable). The adapter also documents an identity reset when no player emission exceeds three strides.

The eligible denominator is player rows, selected explicitly by `cls`; ball rows are not silently included.

| Table | Player rows (eligible denominator) | Ball rows | All rows |
|---|---:|---:|---:|
| `tennis_ref01` | 1430 | 431 | 1861 |
| `tennis_01` | 16766 | 2671 | 19437 |
| `tennis_02` | 1504 | 133 | 1637 |

## Out-of-bounds distribution

Distance outside is Euclidean distance to the declared 78 by 36-foot rectangle; zero-distance rows are not in this distribution. A 6-foot margin would be too cramped for a player run-off. As a generous descriptive run-off yardstick, this audit uses 21 feet beyond each baseline and 12 feet beyond each sideline; those values are not a threshold or gate.

| Table | Player rows outside plane | Fraction | Outside distance ft: median / p90 / p99 / max | Rows beyond generous run-off |
|---|---:|---:|---|---:|
| `tennis_ref01` | 196 | 13.7063% | 1.661 / 7.331 / 9.166 / 12.628 | 0 |
| `tennis_01` | 12805 | 76.3748% | 3.325 / 16.849 / 25.928 / 33.985 | 1171 |
| `tennis_02` | 1140 | 75.7979% | 4.723 / 12.586 / 24.211 / 29.626 | 57 |

These are descriptive counts, not failures: players can legitimately run beyond a painted baseline. The `tennis_01` and `tennis_02` distributions nevertheless have long outside tails even after the generous run-off description.

## Speed distribution using actual frame gaps

For every consecutive observation of each player `track_id`, speed is `Euclidean displacement * declared source_fps / actual frame gap`. No assumed stride is used. `tennis_ref01` uses declared 29.97 fps; the two G219b tables use 59.94005994005994 fps. Nonpositive-gap pairs excluded: zero in every table.

The approximately 29 ft/s elite-sprint value and its generous 58 ft/s multiple are reference yardsticks only, never bars. A pair beyond either reference is a descriptive count, not a failure.

| Table | Speed pairs | Actual gap frames: median / p90 / p99 / max | Speed ft/s: median / p90 / p99 / max | Beyond 29 ft/s reference | Beyond 58 ft/s reference |
|---|---:|---|---|---:|---:|
| `tennis_ref01` | 844 | 3 / 9 / 9 / 9 | 4.627 / 14.963 / 38.739 / 488.767 | 20 (2.3697%) | 4 (0.4739%) |
| `tennis_01` | 16230 | 6 / 6 / 12 / 18 | 4.311 / 15.956 / 44.004 / 1082.824 | 404 (2.4892%) | 124 (0.7640%) |
| `tennis_02` | 1090 | 6 / 6 / 6 / 12 | 4.536 / 19.447 / 68.649 / 402.273 | 50 (4.5872%) | 15 (1.3761%) |

The known `tennis_01` 108.390727-foot movement over six frames is represented here as roughly 1082.824 ft/s, because the calculation uses its actual six-frame gap and declared 59.94005994005994 fps.

## Player IDs per emitted player frame

Committed evidence does not establish whether these three clips depict singles or doubles; therefore the singles-specific `>2` conclusion is **UNDETERMINED**. The distributions are still reported as requested. Each emitted player frame has exactly two distinct player IDs: `tennis_ref01` 715 frames, `tennis_01` 8383 frames, and `tennis_02` 752 frames. There are zero emitted player frames with more than two IDs. Fewer-than-two frames cannot be observed in a table that contains only emitted player rows.

## Epoch-boundary co-occurrence (decision-relevant test)

Definition: an identity-epoch boundary row is the first or last emitted row of a `track_id`; a speed-edge pair is the first or last consecutive within-track pair. The retained CSV cannot score the unobserved inter-ID reset interval, so it cannot attribute a speed to the no-emission gap that created a new ID. This is especially material for `tennis_02`, where G219b already established 189 one-frame two-ID epochs: a one-frame track supplies no speed pair.

| Table | All speed pairs at track edge | Pairs beyond 29 ft/s at edge | Share of beyond-reference pairs at edge | Beyond-reference pairs in tracks <=2 rows |
|---|---:|---:|---:|---:|
| `tennis_ref01` | 466 / 844 (55.2133%) | 10 / 20 | 50.0000% | 0 / 20 |
| `tennis_01` | 652 / 16230 (4.0173%) | 14 / 404 | 3.4653% | 0 / 404 |
| `tennis_02` | 64 / 1090 (5.8716%) | 9 / 50 | 18.0000% | 1 / 50 |

Out-of-bounds rows at first/last identity emissions are also descriptive: 132/196 (67.3469%) in `tennis_ref01`, 709/12805 (5.5369%) in `tennis_01`, and 308/1140 (27.0175%) in `tennis_02`.

The answer to the decision-relevant available-table test is therefore no for `tennis_01` and `tennis_02`: their beyond-29-ft/s pairs are not mostly at observed track edges, and virtually none are in two-row-or-shorter tracks. `tennis_ref01` is exactly split (10 of 20) rather than concentrated. This does not rule out unobserved reset-interval artefacts; the CSV has no manifest/candidate evidence to test those intervals, and the `tennis_02` one-frame epochs make that absence consequential.

## What these outputs are worth

The median and p90 within-track speed distributions are moderate, but all three tables contain a descriptive high-speed tail and the two G219b tables place about three quarters of player rows beyond the declared court plane. The available boundary test does not support explaining most high-speed observations as observed identity-epoch-edge events. These coordinates are therefore usable as a record of what these three tables emitted, but not as evidence that the positions are broadly correct.

Physical plausibility is necessary, never sufficient: a completely wrong coordinate can look physically plausible. This audit provides no ground truth and does not show that any coordinate is correct. It describes only these three clips from a non-deterministic historical route, not a stable population. Bounds inherit the adapter's 78 by 36-foot court model; a different real-court interpretation would change the bound statistics.

No gate and no threshold were introduced, moved, proposed, or applied. Physical references describe distributions only.

## Reproduction, contract self-check, and NOT VERIFIED

Run locally:

```text
python scripts/platformkit/tracking/g230_physical_plausibility.py docs/evidence/tracking/g219_inputs/tennis_ref01_tracking_data.csv docs/evidence/tracking/g219b_inputs/tennis_01_tracking_data.csv docs/evidence/tracking/g219b_inputs/tennis_02_tracking_data.csv --output docs/evidence/tracking/g230_physical_plausibility_audit_2026-09-04.json
python -m pytest scripts/platformkit/tracking/test_g230_physical_plausibility.py -q
```

The focused test passed: `1 passed`. The JSON artifact is `docs/evidence/tracking/g230_physical_plausibility_audit_2026-09-04.json`; it contains all unrounded values and named input paths. Contract self-check: B1 uses every player row and names `cls` exclusions; B2-B4 change no schema or claim lifecycle; B5 does not deploy; B6 moves no modules; B7 has no sampled renders; B8 fits no model; B9 uses real player rows and frame IDs; B10 changes no gate/bar. A7: this memo and the JSON artifact both exist before commit. A12 does not apply because no allowlisted file grew.

NOT VERIFIED: singles versus doubles for these clips; source-video identity/ground truth; the reason for each unobserved no-emission interval; the historical route's repeatability; and correctness of any emitted coordinate.
