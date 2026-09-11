VERDICT: PARTIAL -- 59 of 60 sealed windows measured (720p60 30/30; 1080p30 29/30). The frozen mask admits 3,075 of 19,087 sealed rows with zero forbidden admissions; no target is qualified and nothing is deployed.

Prereg `docs/evidence/tracking/g402_mixed_provenance_target_mask_2026-09-11/prereg.md`, sealed alone at 6120fc58f, SEAL `0bfd1363cc6df3796e11894c7973062c2078ee9aa2c0951961b114d238cd4955`. No bar moved.

Fix 1b (2026-09-11): sealed-window scope excludes 2,347/21,434 overrun rows, including 317 formerly admitted rows; every derived record is now bounded to [start_frame, start_frame+frames).
The failed 1080p30 window is an UNKNOWN coverage row (60 rows total); three out-of-window audit cards were replaced at their original ordinals and prior images retained.
The four findings were scope, coverage, eye-check, and model identity; 5 producer models are now recorded with path, bytes, and SHA-256, while 2 non-producer models are NOT exercised.
This is a post-hoc pod identity receipt after the run against the unchanged deploy tree, whose route files re-hash unchanged; aggregate launch SHA-256 is `a167df3e58ff0e01842a1e724d1ad93b2586ca8f7898a9b11eb0421356a9fbda`.

Fix 1c (2026-09-11): the initially omitted `g402_tables.py` and `g402_repeat.py` are committed, and their LF writers regenerate the derived tables. All 60 cards now use the exact sealed even draw with raw bbox fields (0 degenerate boxes); the earlier non-even cards and degenerate boxes are superseded. This heading replaces the ambiguous Limits heading; no acceptance bar moved.

## Premise and route

The whole-set census remains COMPLETE: 40 eligible 1080p30 sections over 14 games and 79 eligible 720p60 sections over 16 games. G380 remains reproduced at CLAMP 85,333, SUBPIXEL 2,749, fraction 0.968790, receipt/transport 30/30, and unchanged-column identity 0/30. All 22 patch anchors matched the read-only deploy; the scratch route digest is unchanged across 60 launches.

The producer cap was applied after stride, so raw tables are immutable evidence of the overrun. Derived tables filter each launch to its sealed source-frame interval. Raw rows are 10,315/11,119; sealed rows are 9,146/9,941. The sole failed planned window, `1080p30/RIrGQJ_jsGQ_s90`, was preflight-rejected and was not retried or replaced.

## Sealed accounting

| metric | 1080p30 | 720p60 |
|---|---:|---:|
| complete / planned | 29 / 30 | 30 / 30 |
| sealed rows / raw rows | 9,146 / 10,315 | 9,941 / 11,119 |
| candidates / sealed rows | 1,565 / 9,146 | 1,510 / 9,941 |
| candidate frames / sealed source frames | 1,019 / 9,000 | 1,014 / 18,000 |
| evaluated ticks | 2,500 | 2,810 |
| evaluated ticks with candidate | 1,019 | 1,014 |
| receipt equals bounded trace | 29 / 29 | 30 / 30 |
| held pairs / shared pairs | 4,379 / 7,534 | 4,684 / 8,037 |

`coverage_per_section.csv` has 60 rows, including the failed UNKNOWN row. `evaluated_ticks.csv`, `held_pairs.csv`, `provenance_counts.csv`, and `target_mask.csv` contain only complete, sealed records. The cross-tab remains CLAMP 9,354, PREDICTION 5,259, SUBPIXEL 1,399, DETECTION 3,075, HELD 0. Masked-class, repeated-coordinate, or unbound admissions: 0.

## Audit and reproduction

The sealed decision set supplies 30 cards per kind in preregistered draw order. All 60 cards are re-rendered; their previous bytes are retained at `renders_pre_fix1c/`. The audit has 60 rendered cards, 206 boxes, 5 silence cards, 0 degenerate boxes, and 34 boxes extending past a native boundary. It checks transport and coordinate mapping only.

Two fresh processes recompute derived tables from immutable raw bytes and all exact-even cards; `repeats.json` records identical delivered digests. `SHA256SUMS` declares its byte domain on line 1. The Q6 scan covers changed text artifacts and reports counts only.

## NOT VERIFIED / limits

- One 1080p30 window is unmeasured; the verdict remains PARTIAL.
- The post-hoc model identity receipt does not independently verify model identity at traversal time.
- Results apply only to these sealed ten-second scratch windows and one producer run; they do not establish general performance or coordinate truth.
- Thirty-four detector boxes extend past a native boundary; cards retain and draw those raw boxes, but this audit does not validate their geometry.
- No production deployment, training caller, identity repair, or target qualification follows from this diagnostic.
