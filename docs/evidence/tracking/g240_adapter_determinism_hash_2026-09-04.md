# G240 adapter emitted-table hash measurement - 2026-09-04

## Verdict

**ACCEPT (measurement only): the three emitted `tracking_data.csv` files are byte-identical on THREE RUNS, ONE CLIP, ONE CONFIGURATION.** The three SHA-256 values are identical, and an independent row-by-row comparison found zero differing row positions in every pair. This is evidence that the basketball adapter did not vary on these three draws; it is not a claim that the adapter is deterministic.

This executes `docs/evidence/tracking/specs/G240_spec.md` (6,822 bytes) and applies `docs/evidence/tracking/VERIFIER_CONTRACT.md` (11,979 bytes). It changed no production code, `src/`, `domains/`, legacy route, legacy table, threshold, coordinate contract, daemon, keeper, corpus source, or pod checkout.

## Machine, hold discipline, input, and command

Machine: shared RTX 3090 pod `/workspace/nba-ai-system`, because both the named corpus file and the unchanged direct adapter route are pod-resident. The first exact-process check was discarded because it matched the checker itself. The corrected check found no `scripts.platformkit.adapter_run` measurement process, and the run began at token `2026-09-04T08:43:04Z`. During the sequence, run 1 and then run 2 were observed active and left uninterrupted; a separately launched worker saw run 2 active at `2026-09-04T08:45:58Z`, wrote a `held_active_adapter_measurement` record, and exited without touching it. Permanent residents remained present: `keep_track_daemon.sh`, `track_daemon`, `inplay_capture_runner`, and `foundry_runner`.

| Input opened | Full path | Bytes | Resolution | Declared frames | Duration |
|---|---|---:|---:|---:|---:|
| WNBA corpus video | `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4` | 2,931,985,407 | 1920x1080 | 174,430 | 5,814.354 s |

Each run used this unchanged direct route, with only the output game ID different:

```text
cd /workspace/nba-ai-system
/usr/local/bin/python -m scripts.platformkit.adapter_run basketball \
  data/footage_corpus/wnba__wnba_01.mp4 <game_id> --max-frames 6000
```

## Headline: emitted CSV content hashes

| Run | New tracking directory | Data rows | CSV bytes | SHA-256 |
|---:|---|---:|---:|---|
| 1 | `/workspace/nba-ai-system/data/tracking/g240_basketball_hash_20260904T084304Z_r1` | 64,171 | 9,900,631 | `979b0e2ec9820fbeadad9d640a555b37b61405916b08b03d6bda40480e49df75` |
| 2 | `/workspace/nba-ai-system/data/tracking/g240_basketball_hash_20260904T084304Z_r2` | 64,171 | 9,900,631 | `979b0e2ec9820fbeadad9d640a555b37b61405916b08b03d6bda40480e49df75` |
| 3 | `/workspace/nba-ai-system/data/tracking/g240_basketball_hash_20260904T084304Z_r3` | 64,171 | 9,900,631 | `979b0e2ec9820fbeadad9d640a555b37b61405916b08b03d6bda40480e49df75` |

The retained CSVs are the full emitted tables. Every has the same 16-column header, beginning `frame,track_id,cls,x,y` and ending `source_fps,source_height,source_duration`.

## Independent content comparison

The pod reread all three retained CSVs after completion, recomputed every SHA-256 from raw bytes, counted data rows independently of the hash, and compared every table pair row by row. The result is zero in every content-difference field:

| Pair | Row-count difference | Differing row positions | Differing columns | Coordinates | Track IDs | Ordering only | Last-decimal float only |
|---|---:|---:|---|---|---|---|---|
| 1 vs 2 | 0 | 0 | none | no | no | no | no |
| 1 vs 3 | 0 | 0 | none | no | no | no | no |
| 2 vs 3 | 0 | 0 | none | no | no | no | no |

There is therefore no row-level discrepancy to localise: neither coordinates, track IDs, row ordering, nor floating-point serialization differed. This is the content test G225 did not perform; G225's equal row counts alone did not establish it.

## Disk guard, cleanup, and code identity

`df` was not used. The strict initial worker ran `dd if=/dev/zero ... bs=1M count=4 conv=fsync` before run 1 and removed its 4,194,304-byte probe; its strict `set -e` control flow reached run 1 only after that probe passed. The foreground transport closed before it returned the initial `du` values, so they are not reconstructed or invented here. A final independent guard recorded `du -sm /workspace/nba-ai-system/data = 32,735 MB` before and after its removed 4,194,304-byte probe; its SHA-256 was `bb9f8df61474d25e71fa00722318cd387396ca1736605e1248821cc0de3d3af8`.

The named temporary worker artifacts were inventoried, then removed and confirmed absent: 327 bytes of worker result/log files. The two explicitly measured probes plus those artifacts freed **8,388,935 bytes**. No corpus input, emitted CSV, or report was deleted; the three tracking directories and their reports are the measurement outputs, not temporary artifacts.

The pod is not a Git checkout. SHA-256 identities of the exercised route files were: `scripts/platformkit/adapter_run.py` `e4abc2f5e4e4fb2a977ca6beb2fed854e33e829eb0a5d96cef8645680f6181c5`; `domains/basketball/tracking/adapter.py` `1ecf483df26b19c44d1fa25297caed845e5952fbfdd9b704f95a6125f4366c15`; `domains/basketball/tracking/geometry.py` `3bb48c415131358b4512c795ffba30fa9d88a32c56aefd67ef6958c6a747ea5e`; `scripts/platformkit/detection/shim.py` `a25ef1fb801d3770546711601dcbaacaf599778d01e01bf18d6432140718b6d7`; `scripts/platformkit/coordinate_provenance.py` `7532a9a63defee149ee88dd6df12e6b247b14388a8d9a3e4a74e5b3268e10f83`; `scripts/platformkit/tracking_media_inventory.py` `b9e1d0d70064566d360dc8dec8813d6c936998f14f30fb0530e8596aaef989f0`; `scripts/platformkit/tracking_timebase.py` `0dc67ff28e40e1c8b1dba9b191ea5f61d3b15f8904167402c54e9e75c2e2300c`; `scripts/platformkit/tracking_harness.py` `59f60428c5e82460f13e009a04db05d0b27e4a567aff33a324fb7b40bea87f1d`; `scripts/platformkit/tracking_schema.py` `72d21ae1dddded5bc6903dcbbd442de3f47240d5491305c1b6bd933bd007197e`; and `scripts/platformkit/tracking/run_environment.py` `5129bb37e4e23aba93883239078825292136feb331c82ac85c56ee31298cb931`.

## Verifier self-check and NOT VERIFIED

- A2: the headline hashes and row counts were recomputed directly from the three retained CSVs after completion.
- A5 and A12: no schema field, reader, or allowlisted source file changed. No test was needed because no harness was added or changed.
- A7: this committed evidence path exists before commit. The three named pod output directories and their CSV/report paths were confirmed present during recomputation.
- B1/B9: all data rows in every emitted table were counted; no rows were excluded and the named denominator is three whole emitted tables.
- B2-B6/B10: no schema, reader, lifecycle, gate, deployment, threshold, or route implementation changed.
- B7/B8: there is no render or fitted residual; the comparison is exhaustive over every byte and row of every emitted table.
- B11: this is three fresh adapter processes, not a single-run system property.

NOT VERIFIED: repeatability on another clip, model, frame bound, machine, load state, adapter configuration, or future software revision; detection correctness, localization, identity correctness, calibration, court coordinates, or any legacy-route behavior. The shared pod's permanent residents remained active, so this is not a clean-machine result. A content difference would not have contradicted G225 because G225 claimed only equal row counts. Nothing here explains or tests the legacy route's separately unresolved non-determinism.
