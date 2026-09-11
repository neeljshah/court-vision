VERDICT: DONE PROPOSED ONLY -- arm C meets the sealed inherited first-excluded extent bar on 30/30 exact G401 timelines; no patch was applied or executed.

# G408 -- presentation-time duration stop: mechanics and un-applied proposal

No deployment, restart, flag change, registry write, producer integration, or patched-module execution is authorized.

## Exact G401 input and anomalies

The sealed inputs are the 30 rows copied from landed G401 `pts.csv` plus one retained exact frame-PTS stream per draw source in `g401_frame_pts/`; `g401_frame_pts_manifest.csv` binds every stream to a rehashed retained original. All three arms replay those same streams. `source_receipts.csv` records 30/30 source digest matches and the G401 endpoint reproduction. `pts_anomalies.csv` archives every G401-classified duplicate, dropped, backward, and missing event. The known `nba__1rZZ_7buX_Y_s5474.mp4` receipt is 26 duplicate and 26 dropped frames, matching G401.

## Results and endpoint definitions

Arm A (3000-frame) reaches the inherited G401 bar on 0/30; arm B (ceil(100 x validated FPS)) on 29/30. Arm C has 30/30 DEADLINE, 30/30 containment, 0 UNKNOWN, and 0 EOF_SHORT. The inherited unrounded check is `abs(first_boundary_extent_s - 100.0) <= 1/fps`, evaluated before CSV formatting from first excluded PTS minus first PTS, and is 30/30. `last_admitted_gap_s` and the restored `endpoint_gap_s` alias remain descriptive only.

## Proposed integration (text only)

`PROPOSED_g408_pts_duration.diff` validates missing, backward, deadline, and positive-infinity PTS before its stride `continue`; non-finite PTS terminates UNKNOWN. It checks an explicit cap before the next read, making a cap/deadline tie FRAME_CAP, and records `last_admitted_pts` only after a processed frame. The proposal preserves legacy argv, stride calculation, and `_VRAM_FLUSH_INTERVAL = 3000`; it passed `git apply --check` only against pristine scratch bases and was not applied or executed.

## Reproduction and scan

Two fresh processes regenerate every table and all 30 cards from only the sealed evidence inputs. `repeats.json` records both repo-relative commands, return codes, stdout, and per-table/card digests. Q6 is field-aware, records pattern indices, and has 0 non-opaque hits.

## Fix 1b (2026-09-11)

After codex-sol REJECT x1, Fix 1b sealed the exact G401 frame-PTS streams and every anomaly, restored the unrounded inherited bar, and moved proposal validation before prefetch stride filtering. Its last-admitted-span implementation and removed aliases are retained only under `pre_fix1c/`.

## Fix 1c (2026-09-11)

After codex-sol REJECT x2, Fix 1c restores first-boundary extent to the inherited first-excluded definition and reports arm C 30/30 under that sealed bar. It restores prior receipt/index aliases, adds positive-infinity and cap/deadline-tie fixtures, and refreshes all tables, cards, repeats, scan, and hashes.

## Artifact SHA-256

- `g401_pts_rows.csv` f216edca77f46aedc598032d2ca1fa662942f9124fd4de473e18d2930a3e00db
- `g401_frame_pts_manifest.csv` ee40902973b3962f84d837bee79e531176caac3d5f76d041692314311a7ec4f6
- `scripts/platformkit/tracking/g408_tables.py` 64fb7516acc4aa4cba37ecdde008c540b4d2a5139a0c1df3150a2c66c6ff7149
- `scripts/platformkit/tracking/g408_build.py` e3a9fd5febcf76b5c007386cea4c1fe9b89f3e9fd65a52d9fd66019ca46d12a2
- `scripts/platformkit/tracking/g408_stop.py` 6331c0eb16d8213885e24d4c120b4362df4bc277577716e4c5494a8ae373322b
- `scripts/platformkit/tracking/g408_q6.py` 4d116c36f3a551460b27f1175441a4b4a2915995755f9f9a48f5ca4a7238b83f
- `tests/platformkit/test_g408_pts_stop_proposal.py` fda843941e0092cc1b66d2d0cdcd3eabbfcf19d10537d4b6aa6334b6d865d603
- `source_receipts.csv` 96f40cda8f5ff141cf6f72fa95ea5f4933e3f1cd53ba3b9f725caec13c0a4323
- `admitted_indices.csv` 0e378f25ac5f38ff922422ad1591eca414f069d653093a80084ac63c36055318
- `paired_stops.csv` 20348af6f30f0332f6c4a45ba6add7efdb9f9ebf7997e9f6db1bc588198868f0
- `PROPOSED_g408_pts_duration.diff` CRLF e71b46b970e1d5a20ee87b5e3ca9007cc27527fb11ed64d22ae5b281ef90dfa8; LF 231aa89afac76ad47cfc002386c1b6e36e2c62cd777d5970e2822b36530df5d4
- `proposal_checks.json` 2800c826deb959d58cd86baca1e73165cd87c292f157701caaa8013b7fc29d43
- `repeats.json` 78d64ae4e77c8bee01a0f89200c14daae9f405654206a81ffd059da13b00e599
- `q6_scan.json` 443c54ed3ba3a264008388e0a93016531b66fd0a1430b5200c64af0f076f8bb3
- `summary.json` 3bb7648a20016f1fd23f46da989fab55b1eea4f8344926ecbe2562bfae20ee4b
- `SHA256SUMS` declares the byte domain and inventories every evidence file except itself.

## NOT VERIFIED

- Runtime resource use or output quality after the existing 3000-frame flush boundary.
- Decoder PTS behavior on the production route, or any patched-module behavior.
- Any deployment, daemon action, feature flag change, registry write, or real-time producer integration.
