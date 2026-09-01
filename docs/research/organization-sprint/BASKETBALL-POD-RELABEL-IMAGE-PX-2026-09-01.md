# Basketball pod relabel: image_px teacher data

Run on the basketball pod at 2026-09-01 with `nice -n 15`:

```text
python -m scripts.platformkit.basketball_relabel_image_px
```

The 16:19 scale check is struck. These rows have no persisted court
calibration sidecar, so they are not basketball registration evidence. The
relabeler retained raw source pixels in `x` and `y`, discarded the wide source
columns (including every feet-labelled field), stamped `coordinate_space` as
`image_px`, and recorded `coordinate_calibration_reason` as
`no_court_calibration_sidecar`.

Each source was copied beside itself to `tracking_data.csv.pre_relabel` before
the rewrite. The frozen harness was run before and after every rewrite. Its
required result is `FAIL`: `image_px` is a preserved teacher corpus and never
a scorable court-coordinate game.

| Game | Rows | Frames | Before | After |
| --- | ---: | ---: | --- | --- |
| ncaa_basketball_IB-_u4gW3ds | 3,061 | 578 | FAIL | FAIL |
| ncaa_basketball_sRtHQbywiTE | 2,234 | 745 | FAIL | FAIL |
| ncaa_basketball_tiUvyvWOCxo | 4,424 | 978 | FAIL | FAIL |
| ncaa_basketball_zqBCKovJCQU | 5,303 | 999 | FAIL | FAIL |
| wnba_01 | 4,855 | 999 | FAIL | FAIL |
| wnba_02 | 5,342 | 1,000 | FAIL | FAIL |
| wnba_03 | 2,380 | 971 | FAIL | FAIL |
| wnba_04 | 4,906 | 997 | FAIL | FAIL |
| wnba_05 | 2,230 | 547 | FAIL | FAIL |
| wnba_kangps_g1 | 38,424 | 5,730 | FAIL | FAIL |
| wnba_kangps_g2 | 29,850 | 5,987 | FAIL | FAIL |

All 11 backups exist. No post-relabel harness result passed, so the
pre-registered restore-and-stop kill condition did not fire.

Validation: `python -m pytest scripts/platformkit/test_basketball_relabel_image_px.py -q`
returned `1 passed` in the worktree. The pod Python environment has no pytest,
so no package was installed there; the relabeler's actual frozen-harness run is
the pod-side verification recorded above.
