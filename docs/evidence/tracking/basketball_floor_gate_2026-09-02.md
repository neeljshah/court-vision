# Basketball IMAGE_PX floor gate - 2026-09-02

## Scope

G25 tests an additive ON-FLOOR tag at the IMAGE_PX rung. It reads the eight
relabeled tables from `/tmp/t3b_reemit/` and their matching source videos. For
each tracked-frame interval (`max(table.frame) + 1`), it learns one HSV hue and
saturation reference from lower-middle frame medians, keeps the largest
court-color connected component in each frame, and dilates it by 3 percent of
frame height. Rows outside that dilated region are retained and stamped
`observation=nonfloor`; all others retain `observed`.

`tight_shot` is a report-only per-frame flag when the undilated mask covers less
than 15 percent of the frame. It does not drop a row. The first pod attempt
incorrectly used complete source videos rather than the tracked interval. It
was left running, never used, and the table below comes only from the separate
tracked-interval output `/tmp/g25_floor_gate_tracked/`.

The output table preserves every input row. Containment is calculated over all
rows before and after tagging, not only observed rows.

## Pod measurement

Command (from `/workspace/nba-ai-system`):

```text
nohup setsid nice -n 15 python -m scripts.platformkit.tracking.basketball_floor_gate --in /tmp/t3b_reemit --out /tmp/g25_floor_gate_tracked --footage-root data/footage_corpus --render-games wnba_04 ncaa_basketball_IB-_u4gW3ds --render-count 8 > /tmp/g25_tracked.log 2>&1 < /dev/null &
```

| game | rows | nonfloor rows (share) | tight frames (share) | containment all before = after | top 20 pct frame: floor share | top 20 pct frame: nonfloor share |
|---|---:|---:|---:|---:|---:|---:|
| ncaa_basketball_IB-_u4gW3ds | 3,061 | 1,111 (36.30%) | 507 / 2,002 (25.32%) | 0.9827 = 0.9827 | 33.36% | 23.10% |
| ncaa_basketball_sRtHQbywiTE | 2,234 | 1,045 (46.78%) | 1,234 / 3,898 (31.66%) | 0.9749 = 0.9749 | 0.00% | 0.18% |
| ncaa_basketball_tiUvyvWOCxo | 4,424 | 1,728 (39.06%) | 450 / 3,268 (13.77%) | 0.9424 = 0.9424 | 0.23% | 1.11% |
| ncaa_basketball_zqBCKovJCQU | 5,303 | 2,899 (54.67%) | 1,000 / 5,698 (17.55%) | 0.9370 = 0.9370 | 0.38% | 2.53% |
| wnba_01 | 4,855 | 4,815 (99.18%) | 2,998 / 2,998 (100.00%) | 0.9489 = 0.9489 | 0.00% | 5.68% |
| wnba_02 | 5,342 | 4,971 (93.06%) | 1,203 / 3,178 (37.85%) | 0.9672 = 0.9672 | 0.00% | 27.39% |
| wnba_04 | 4,906 | 4,755 (96.92%) | 715 / 3,628 (19.71%) | 0.9576 = 0.9576 | 0.08% | 40.75% |
| wnba_05 | 2,230 | 1,496 (67.09%) | 3,506 / 4,348 (80.63%) | 0.9493 = 0.9493 | 13.99% | 11.61% |

The last two columns re-read the originally suspicious top-of-frame share as
floor versus nonfloor. For example, the `wnba_04` top-band share is 40.83% of
all rows: 0.08% is floor-tagged and 40.75% is nonfloor-tagged. This is not a
containment result and no row was removed to produce it.

Per height band, `before -> after` is the nonfloor share within that band. The
source tables had only `observation=observed`, so every before value is 0.0.

| game | 0-20 pct | 20-40 pct | 40-60 pct | 60-80 pct | 80-100 pct |
|---|---:|---:|---:|---:|---:|
| ncaa_basketball_IB-_u4gW3ds | 0.0 -> 40.9 | 0.0 -> 28.8 | 0.0 -> 100.0 | 0.0 -> 100.0 | 0.0 -> na |
| ncaa_basketball_sRtHQbywiTE | 0.0 -> 100.0 | 0.0 -> 60.4 | 0.0 -> 33.0 | 0.0 -> 14.3 | 0.0 -> 81.8 |
| ncaa_basketball_tiUvyvWOCxo | 0.0 -> 83.1 | 0.0 -> 75.5 | 0.0 -> 20.4 | 0.0 -> 23.7 | 0.0 -> 77.2 |
| ncaa_basketball_zqBCKovJCQU | 0.0 -> 87.0 | 0.0 -> 37.7 | 0.0 -> 43.4 | 0.0 -> 39.4 | 0.0 -> 81.7 |
| wnba_01 | 0.0 -> 100.0 | 0.0 -> 99.7 | 0.0 -> 98.4 | 0.0 -> 100.0 | 0.0 -> 100.0 |
| wnba_02 | 0.0 -> 100.0 | 0.0 -> 95.8 | 0.0 -> 76.6 | 0.0 -> 52.4 | 0.0 -> 75.0 |
| wnba_04 | 0.0 -> 99.8 | 0.0 -> 97.0 | 0.0 -> 88.8 | 0.0 -> 72.7 | 0.0 -> 100.0 |
| wnba_05 | 0.0 -> 45.4 | 0.0 -> 70.6 | 0.0 -> 80.5 | 0.0 -> 92.9 | 0.0 -> 100.0 |

## Render-and-look

Yellow is the dilated floor-mask outline; green is `observed`; red is
`nonfloor`. All 16 evenly spaced renders were viewed.

NCAA `IB-_u4gW3ds`: [0](basketball_floor_gate_2026-09-02/ncaa_basketball_IB-_u4gW3ds_f000000.png), [285](basketball_floor_gate_2026-09-02/ncaa_basketball_IB-_u4gW3ds_f000285.png), [571](basketball_floor_gate_2026-09-02/ncaa_basketball_IB-_u4gW3ds_f000571.png), [857](basketball_floor_gate_2026-09-02/ncaa_basketball_IB-_u4gW3ds_f000857.png), [1143](basketball_floor_gate_2026-09-02/ncaa_basketball_IB-_u4gW3ds_f001143.png), [1429](basketball_floor_gate_2026-09-02/ncaa_basketball_IB-_u4gW3ds_f001429.png), [1715](basketball_floor_gate_2026-09-02/ncaa_basketball_IB-_u4gW3ds_f001715.png), [2001](basketball_floor_gate_2026-09-02/ncaa_basketball_IB-_u4gW3ds_f002001.png).

WNBA `wnba_04`: [0](basketball_floor_gate_2026-09-02/wnba_04_f000000.png), [518](basketball_floor_gate_2026-09-02/wnba_04_f000518.png), [1036](basketball_floor_gate_2026-09-02/wnba_04_f001036.png), [1554](basketball_floor_gate_2026-09-02/wnba_04_f001554.png), [2072](basketball_floor_gate_2026-09-02/wnba_04_f002072.png), [2590](basketball_floor_gate_2026-09-02/wnba_04_f002590.png), [3108](basketball_floor_gate_2026-09-02/wnba_04_f003108.png), [3627](basketball_floor_gate_2026-09-02/wnba_04_f003627.png).

| sampled game | displayed tags | visual result |
|---|---:|---|
| ncaa_basketball_IB-_u4gW3ds | 9 green + 5 red | 14 / 14 tags correct: green feet on court; red on a referee/crowd/torso detection outside the floor. |
| wnba_04 | 0 green + 19 red | 19 / 19 tags correct: red detections are bench/crowd-side people rather than on-court feet. |
| total | 9 green + 24 red | 33 / 33 tags correct in the selected rows. |

The semantic tight-shot flag matches 14 of 16 selected frames. It misses two
close WNBA player shots (frames 0 and 2072) because enough court-color pixels
remain connected to exceed the 15 percent area threshold. The yellow outline
also regularly includes score graphics and nearby bodies, so it is not a clean
court boundary.

## Honest verdict

**FAIL AS A GENERAL FLOOR GATE.** The tag is additive, the requested
rendered-row labels are correct, and full-table containment is byte-for-byte
unchanged. But the fixed HSV/largest-component design fails catastrophically at
the Atlanta Dream's **Gateway Center Arena** (`wnba_01`): it tags 4,815 / 4,855
rows (99.18%) as nonfloor and marks all 2,998 / 2,998 frames tight-shot despite
the wide on-court view in the prior evidence render. `wnba_02` and `wnba_04`
also have implausibly high nonfloor shares (93.06% and 96.92%). The learned
lower-middle color can represent a painted apron, crowd, or broadcast graphic
rather than hardwood, and largest-component selection cannot repair that.

This result must not be used to exclude rows from G04 teacher features or to
claim tracking improvement. The module remains an offline, report-only
annotation utility. A future candidate needs an independently validated
court-segmenter or line/geometry evidence; do not tune hue/saturation bands
against these viewed games.

## Verification and limits

```text
python -m pytest scripts/platformkit/tracking/test_basketball_floor_gate.py -q
# 1 passed in 2.94s
```

- The only local test is synthetic; it proves a hardwood/crowd mask, tag,
  tight flag, and unchanged all-row containment. It does not validate an arena.
- The pod has no pytest installation; only the local per-file test was run.
- All eight pod outputs are under `/tmp/g25_floor_gate_tracked/`; no corpus
  tracking table, daemon, registry, or feature flag was modified.
