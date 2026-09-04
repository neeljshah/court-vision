# G239 Adapter Run on Amateur Footage - 2026-09-04

## Verdict

**ACCEPT: the unchanged basketball adapter was measured on one bounded fixed-camera amateur-footage clip and reached SCORED.** It emitted an image-space canonical table, then the unchanged harness failed at the expected coordinate contract. This is an emission and track-structure measurement, not tracking-correctness evidence.

This executes `docs/evidence/tracking/specs/G239_spec.md` and `docs/evidence/tracking/VERIFIER_CONTRACT.md`. No production code, threshold, imgsz, confidence, min_players, coordinate contract, harness, daemon, keeper, `footage_corpus`, or `CLIP_SPORTS` entry changed. `src/` and `domains/` were read/imported only.

## Pod hold check, inputs, and disk guard

The pod was `/workspace/nba-ai-system`, because the unchanged GPU adapter route and measurement outputs are pod-resident. At `2026-09-04T07:27:23Z`, before a write, the live preflight found permanent `keep_track_daemon.sh`, `track_daemon`, `inplay_capture_runner`, and `foundry_runner` residents, and no G236, G238, G239, or G226 `adapter_run` process. None was waited on, killed, restarted, or changed.

| Full input path | Bytes | Resolution | Frames | SHA-256 | Use |
|---|---:|---|---:|---|---|
| `C:\Users\neelj\nba-ai-system\data\videos\g220c_amateur_footage\g220c__jh3fnwMi7dM.mp4` | 346,739,796 | 1920x1080 | 28,865 | `ffa37cbb9098c9ffbe65cf4585d3201972652f817631a2bd9ca9b6c005b7717d` | Local source opened and uploaded once |
| `/workspace/g239_amateur_measurement/g220c__jh3fnwMi7dM.mp4` | 346,739,796 | 1920x1080 | 28,865 | `ffa37cbb9098c9ffbe65cf4585d3201972652f817631a2bd9ca9b6c005b7717d` | Temporary pod input outside daemon-watched application data |
| `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4` | 2,931,985,407 | 1920x1080 | 174,430 | G226c-recorded identity; not re-opened | Professional-broadcast baseline |

The source ffprobe values were 30 FPS and 960.100 seconds. The pod copy was never added to `footage_corpus` and was removed during cleanup. `df` was not used.

| Time UTC | `du -sm /workspace/nba-ai-system/data` | `dd conv=fsync` probe |
|---|---:|---|
| 07:27:41, before upload | 32,277 MB | Passed, 4,194,304 bytes, SHA-256 `bb9f8df61474d25e71fa00722318cd387396ca1736605e1248821cc0de3d3af8`; removed |
| 07:29:42, after upload | 32,284 MB | Passed, 4,194,304 bytes, same SHA-256; removed |
| 07:33:03, after cleanup | 32,315 MB | Passed, 4,194,304 bytes, same SHA-256; removed |

The sole bounded invocation was:

```text
cd /workspace/nba-ai-system
/usr/local/bin/python -m scripts.platformkit.adapter_run basketball /workspace/g239_amateur_measurement/g220c__jh3fnwMi7dM.mp4 g239_basketball_20260904T0729Z --max-frames 6000
```

It matches G226c's direct adapter route and bound, did not invoke `run_clip`, and did not pass `--skip-features`. It used 30.0 FPS, stride 3, and a 0.1-second sample interval.

## Retained output and code identity

| Retained pod output | Bytes | SHA-256 |
|---|---:|---|
| `/workspace/nba-ai-system/data/tracking/g239_basketball_20260904T0729Z/tracking_data.csv` | 17,950,507 | `3be93b3b6a87e0aab58e9faf6b5e23d0c2d2c6d5bd1fa05984229e4d3673a217` |
| `/workspace/nba-ai-system/data/tracking_reports/basketball/g239_basketball_20260904T0729Z.json` | 3,320 | `c0a83732745bfd59fea2352bd7b45a3608212d03e4111a6e95bb029155832b08` |

The pod is not a Git checkout. Exercised route-file SHA-256s: `adapter_run.py` `e4abc2f5e4e4fb2a977ca6beb2fed854e33e829eb0a5d96cef8645680f6181c5`; basketball `adapter.py` `1ecf483df26b19c44d1fa25297caed845e5952fbfdd9b704f95a6125f4366c15`; `geometry.py` `3bb48c415131358b4512c795ffba30fa9d88a32c56aefd67ef6958c6a747ea5e`; detection `shim.py` `a25ef1fb801d3770546711601dcbaacaf599778d01e01bf18d6432140718b6d7`; `coordinate_provenance.py` `7532a9a63defee149ee88dd6df12e6b247b14388a8d9a3e4a74e5b3268e10f83`; `tracking_media_inventory.py` `b9e1d0d70064566d360dc8dec8813d6c936998f14f30fb0530e8596aaef989f0`; `tracking_timebase.py` `0dc67ff28e40e1c8b1dba9b191ea5f61d3b15f8904167402c54e9e75c2e2300c`; `tracking_harness.py` `59f60428c5e82460f13e009a04db05d0b27e4a567aff33a324fb7b40bea87f1d`; `tracking_schema.py` `72d21ae1dddded5bc6903dcbbd442de3f47240d5491305c1b6bd933bd007197e`; and `tracking/run_environment.py` `5129bb37e4e23aba93883239078825292136feb331c82ac85c56ee31298cb931`.

## Side-by-side measurements

G239 values were independently recomputed from the retained CSV: direct row count; unique frame and ID values; group-size distributions; duplicate `(frame, track_id)` rows; and inclusive `0 <= x <= 1920`, `0 <= y <= 1080`. The named 6,000 evaluated-frame denominator is independent of rows.

| Measure | G226c professional broadcast | G239 fixed-camera amateur clip | Difference, G239 minus G226c |
|---|---:|---:|---:|
| Evaluated frames | 6,000 | 6,000 | 0 (0.00 pct) |
| Emitted rows | 64,171 | 116,441 | +52,270 (+81.45 pct) |
| Frames with players | 5,972 | 6,000 | +28 (+0.47 pct) |
| Players/frame: min / median / p90 / max | 1 / 11.0 / 16 / 27 | 6 / 20.0 / 24 / 34 | +5 / +9.0 / +8 / +7 |
| Distinct track ids | 207 | 157 | -50 (-24.15 pct) |
| Track length: min / median / p90 / max | 1 / 205 / 730 / 2,270 | 1 / 500 / 1,729.2 / 4,029 | 0 / +295 / +999.2 / +1,759 |
| One-frame tracks | 1 of 207 | 1 of 157 | count 0; share +0.15 percentage points |
| Duplicate `(frame, track_id)` rows | 0 | 0 | 0 |
| Rows inside 1920x1080 | 100.00 pct | 100.00 pct (116,441 of 116,441) | 0.00 percentage points |
| Harness stage | SCORED | SCORED | Same stage |

The G239 per-frame increases are min +500.00 pct, median +81.82 pct, p90 +50.00 pct, and max +25.93 pct. Track-length increases are median +143.90 pct, p90 +136.88 pct, and max +77.49 pct. The CSV declares only `image_px`. The harness verdict is `FAIL`; first failure head, verbatim:

```text
coordinate_contract: rows declare coordinate_space image_px not accepted for sport basketball; a preserved detection corpus is never a scorable game
```

## Direct answer and limitations

On this one fixed-camera amateur clip, the tracker emitted materially more image-space player rows per evaluated frame and longer tracks, while assigning 50 fewer distinct IDs, than in G226c's one moving professional broadcast clip. This is a measured difference in the emitted table only. It neither establishes detection correctness nor says the tracker works correctly on amateur footage.

One amateur clip versus one broadcast clip compares two clips, not two populations. The route is non-deterministic and each side is one draw. Venue, teams, lighting, resolution encoding, and camera geometry differ together, so every difference is confounded and cannot be attributed to production tier or amateur footage alone. Row counts measure emission, never correct locations, identity, calibration, or physical tracking accuracy.

## Cleanup, contract check, and NOT VERIFIED

Removed `/workspace/g239_amateur_measurement/g220c__jh3fnwMi7dM.mp4` (346,739,796 bytes) and `/tmp/g239_adapter_20260904T0729Z.log` (218 bytes), freeing **346,740,014 bytes**. Each 4,194,304-byte probe was removed immediately after its check. The final pod check confirmed the upload and log paths absent; the CSV and report remain as measurement outputs.

Section B self-check: B1 named independent evaluated frames; B2 no schema/readers changed; B3-B4 no gate/claim flow changed; B5 no pod code transfer; B6 no moved module; B7-B8 no renders/residuals; B9 actual row/frame/ID units; B10 no changed bar. A7: this evidence memo exists before commit and retained output paths were checked after cleanup.

NOT VERIFIED: detection correctness, localization, player identities, ball tracking, calibration, court coordinates, repeatability, a population estimate, causal source of any difference, or any conclusion about amateur footage as a class.
