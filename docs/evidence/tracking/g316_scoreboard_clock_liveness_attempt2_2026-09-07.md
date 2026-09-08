# G316 attempt 2 -- scoreboard game-clock liveness, 2026-09-07 23:59 CDT

**VERDICT: CLOSED AT LIMIT for the sealed reader route.** On 372 scoreboard-present frames of 400 sampled across four >= 720p broadcast skins the sealed EasyOCR route yields an `MM:SS` parse on **246, a parsed-clock rate of 0.6613 (Wilson 95 pct [0.6118, 0.7075])** against the spec's 0.90 bar, and **9 of the 20 hand-read tiles agree within 1 s**. The bar is missed on every skin; no bar was lowered (Q3). The denominator is NOT circular: **zero** of the 20 evenly-spaced tiles carried a legible clock the presence rule rejected. Calibration language only; no recall, precision, registration, tracking-quality or harness-pass claim, no `passed` flip, nothing adopted, nothing deployed. Prereg `g316_preregistration_attempt2_2026-09-07.md` seal `23a01551e94d1ab3cbd8e0ab7655886547a53f762c5acf0ea688d244b0820fc4` commit `558771cb4`; device amendment seal `325fc52c07bac989571e698a1e3f1ddfa5a79e160a17f5b9647847295a37002b` commit `637f7d79a`; spec VERSION `2026-09-07b` commit `70252d816` (Q1: both seals predate the first metric).

## Premise (step 0) -- REPRODUCED on the clips this attempt scores, not falsified
| clip | N rows | `scoreboard_game_clock` filled | `scoreboard_period` filled | distinct periods | clip sec |
|---|---|---|---|---|---|
| 0022400909_s900 | 5,603 | **0** | 5,603 | 1,2,3,4 | 132.53 |
| mil_chi_2025 | 2,642 | **0** | 2,642 | 1,2,3,4 | 906.47 |
| ncaa_basketball_zqBCKovJCQU | 6,623 | **0** | 6,623 | 1,2,3,4 | 965.60 |
| wnba_06 | 3,606 | **0** | 3,606 | 1,2,3,4 | 955.80 |

Pod, `data/tracking/<clip>/tracking_data.csv`, via the landing module `--stage premise`: 0 of 18,474 rows carry a clock, and periods 1-4 appear inside a 132.53 s clip.

## Period contradiction -- EXPLAINED (attempt-1 finding, cited, not re-litigated)
`src/pipeline/unified_pipeline.py:4282-4350` `_backfill_scoreboard_period()`, called at `:3001`, fills every empty cell with `q = max(1, min(4, int(frame / max_frame * 4) + 1))` (`:4334-4335`). `q` depends only on the row's position in the file, so it emits 1/2/3/4 over a clip of any length. That fallback, not a scoreboard reading, is what puts periods 1-4 inside a 132.53 s clip. The PROPOSED `src/` diff stays unapplied and local-only at `docs/research/organization-sprint/PROPOSED-scoreboard-period-no-frame-percentile-fill-2026-09-07.md` (worktree a12; `docs/research/` is gitignored).

## Sources actually opened (A9) -- all >= 720p pod sections
Scoring, `/workspace/nba-ai-system/data/footage_corpus/`: `nba__0022400909_s900.mp4` (34,795,729 B, 1280x720, 130.162 s), `nba__mil_chi_2025.mp4` (258,015,436 B, 1280x720, 906.530 s), `ncaa_basketball__ncaa_basketball_zqBCKovJCQU.mp4` (467,936,551 B, 1920x1080, 965.650 s), `wnba__wnba_06.mp4` (430,058,965 B, 1920x1080, 960.033 s). 400 frames, 400 unique, digest `0ba4886b0604caba24476d6bccf7e1a91f9c86470cd355bed72ffce66a1fcb35`. Design clips (disjoint, never scored): `nba__den_phx_2025`, `ncaa_basketball__ncaa_basketball_mRkuGgeECak`, `wnba__wnba_02`, `basketball__g220c_jh3fnwMi7dM`, 160 frames, digest `5c81403157dcc4f0d2062d114a54348b125b089cf3350186c84d08aa38ed3c73`. The module's `--stage extract` re-derived clip C1 and reproduced **100 of 100** scored frame hashes byte-identically.

## Presence rule -- designed on 4 skins, sealed, and NON-CIRCULAR here
Sealed: `white(BOT) >= 0.04 AND edge(BOT) >= 0.07` over `BOT = x[0.00,1.00) y[0.78,1.00)` -- `edge(...)` here is the module identifier `edge_row`, a horizontal-border statistic quoted verbatim, exempt under the Q6 NOTE and never a claim word. Design tally 153 present / 7 absent by eye over 160 frames, agreement **159/160, zero false negatives on all four skins**, one false POSITIVE. On the scoring set it fired on 372 of 400 (rejected 28: C1 7, C2 5, C3 5, C4 11) and on **all 20** hand-check tiles, including the two that carry no clock. It over-accepts, which can only add unreadable frames to the denominator (B1).

## Measurement (n = 400: 100 per clip, evenly spaced by timestamp, no head slice) -- bar 0.90; every skin and the pooled upper bound fall short
| skin | sampled | rule fired | rejected | parsed | parsed-clock rate | Wilson 95 pct | median conf |
|---|---|---|---|---|---|---|---|
| C1 NBA national section | 100 | 93 | 7 | 67 | **0.7204** | [0.6219, 0.8015] | 0.7839 |
| C2 NBA regional | 100 | 95 | 5 | 70 | **0.7368** | [0.6403, 0.8149] | 0.8541 |
| C3 NCAA tournament | 100 | 95 | 5 | 78 | **0.8211** | [0.7320, 0.8852] | 0.8663 |
| C4 WNBA | 100 | 89 | 11 | 31 | **0.3483** | [0.2575, 0.4517] | 0.8014 |
| **pooled** | 400 | 372 | 28 | 246 | **0.6613** | [0.6118, 0.7075] | -- |

## The 20-render hand read (evenly spaced over the FULL 400, model read, declared)
Model-read clock, `abs_error_sec` and the parsed value are in `g316_handcheck_index.json`. 17 tiles carry a clock the model could read; **9 agree exactly (abs = 0.0 s)**; 4 parses are confidently WRONG (t09 hand 1:30 vs parsed 1:05, t10 3:46 vs 6:46, t11 1:39 vs 3:57, t14 3:31 vs 10:02); 4 legible clocks produced no parse; 3 tiles have no model read (t00 a player stat card and t17 no overlay, both no clock; t19 a clock whose seconds digit the model could not resolve under motion blur). **0 legible clocks sat on a rule-rejected frame.**

## Named failure modes (measured, ordered by size)
1. **A non-clock `MM:SS` wins the parse.** Tokens from R1..R4 are unioned before `_parse_scoreboard_text`, whose first `\b(\d{1,2})[:.](\d{2})\b` match wins. t09's 1:05 is the promo line "7-0 IN LAST 1:05"; the NCAA bar carries seed/record strings (17-13, 24-11, 23-8). 4 of 13 comparable tiles are wrong, so the 0.6613 rate is an upper bound on *correct* clocks, not a correctness rate.
2. **Sub-minute renders do not match the production regex.** 39 of the 126 present-but-unparsed frames carry a `SS.S` token (C1 5, C2 14, C3 14, C4 6). Excluding them is CONTEXT only, never the metric: 246/333 = 0.7387, still under 0.90.
3. **Encode quality, not resolution.** C4 (1920x1080) is the worst skin at 0.3483; its bug is heavily motion-blurred and 52 of its 58 non-parses carry no sub-minute token at all. Height alone does not make a clock machine-readable.

**Machine, tests, and what did NOT move.** EasyOCR **1.7.2 on the pod GPU** (RTX 3090), isolated tree `/workspace/ocr_env` installed `--no-deps`; the daemon env's `cv2` is `4.14.0` before and after; `track_daemon` (2 pids) never signalled; free VRAM 16,465 MiB at switch, 18,453 MiB peak of 24,576 MiB. Compute ran in per-worktree scratch `/workspace/wt/a4/g316_scratch`; **0 G316 files exist under the deployed tree** `/workspace/nba-ai-system` (B5). `pod_run` was abandoned mid-setup because three concurrent lanes contended its `du -sm /workspace` guard; the spec's own disk probe returns `DU_CONTEXT=UNKNOWN` at its 60 s timeout, which the spec says never to stop on. A11: `src/tracking/scoreboard_ocr.py` `63ddfd4a...` and module `f3d89ffab98f...` hashed on the pod at run start. `src/tracking/scoreboard_ocr.py` `63ddfd4a05bbac177a4264bb97a232013fbb959184f2f3833bc847efdd6182e4` and `src/pipeline/unified_pipeline.py` `bb92310f54c06ffa4c7caf6bea23861a29c35f3588b6fb4a375aeaf74b6b15f8` are identical before and after; `git status src/` clean. No `tracking_data.csv` column renamed or removed, no ledger `passed` touched, no threshold changed, nothing written under `data/` or `data/registry/`. Tests: `python -m pytest tests/platformkit/test_g316_scoreboard_clock_liveness.py -q -p no:cacheprovider` -> **6 passed**. `python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider` -> **1 passed** (module 299 lines, under the 300 rail, so no A12 allowlist entry was needed).

**Artifacts (SHA-256 head, LF-normalized).** `docs/evidence/tracking/g316_attempt2/`: `g316_premise.json` `c45d5bc81477f7c4`, `g316_design_manifest.json` `e4e8ec1bbe668b3a`, `g316_design_labels_and_rule.json` `4a0e7512b8b5cfa8`, `g316_score_manifest.json` `edd4d1072a7b4082`, `g316_frame_records.jsonl` `1be29d1e007d98e6` (400 records, full declared column set), `g316_liveness_summary.json` `203e4c640334b0ba` (re-hashed at landing, correction 2), `g316_handcheck_index.json` `9a09c72539b702f3`. Renders (`g316_handcheck_sheet.png`, the magnified tile groups and the design contact sheets) are LOCAL-ONLY, and were already absent at verification time as were seven of the eight source-video paths; the committed artifacts above and their SHA-256 heads are the durable record of this row. Would-be deploy list if a verifier accepts: `scripts/platformkit/tracking/g316_scoreboard_clock_liveness.py` only.

## Corrections applied at landing 2026-09-08 (verifier codex-sol)
1. Citation fix (the verifier's one minimal diff): the fallback formula is at `src/pipeline/unified_pipeline.py:4334-4335`, not `:4335-4340`; the enclosing `:4282-4350` explanation stands. Prose above was compressed to hold the 60-line rail, so the `:NN` citations inside `G316_VERIFY_2026-09-08.md` address this memo as of commit `13be14ae6`.
2. NEW GAP (c) closed: the summary JSON omitted the per-broadcast median reader confidence the spec asks for (`specs/G316_spec.md:62`) and the table above reports. Added additively to `g316_liveness_summary.json` as `median_ocr_confidence_present` / `median_ocr_confidence_n`, recomputed from the committed `g316_frame_records.jsonl` over scoreboard-present frames carrying a non-null confidence; it reproduces the table exactly, and no existing field, count or rate changed.
3. NEW GAPs (a) and (b) recorded: (a) the renders and seven of the eight source-video paths are local-only and were absent at verification, so the committed numeric artifacts and their hashes are the durable record; (b) master carried neither the module nor its test until this landing, which lands both.
4. NEW GAP (d) closed -- the full producer trace the spec asks for (`specs/G316_spec.md:101`), cited from the attempt-1 finding, no new measurement:
`src/tracking/scoreboard_ocr.py` scans only a `_TOP_FRAC = 0.10` top strip (`:118`), while the clock on these four skins sits bottom-right -- which is why this attempt's sealed crop region is `BOT y[0.78,1.00)`.
The pod producer environment has NO OCR engine (`easyocr`, `paddleocr`, `pytesseract`, `rapidocr_onnxruntime`, `doctr`, `mmocr` all `ModuleNotFoundError`, no `tesseract` binary), so `_get_reader()` (`:141-175`) raises, `_ocr_frame`'s `except` (`:308-310`) returns `_DEFAULT_STATE` (`:121-134`, `game_clock_sec: -1.0`), and the write site `src/pipeline/unified_pipeline.py:2751-2768` emits an empty clock on every row: the 0 of 18,474 above is mechanical, not a reading.
The route exercised here is therefore NOT the producer's: an out-of-band `--no-deps` EasyOCR 1.7.2 tree on the pod GPU over the bottom strip, with `_parse_scoreboard_text` imported verbatim; the period values still come from `_backfill_scoreboard_period()` as above.
Vocabulary follows contract Q6; automated scan required.

## NOT VERIFIED
- That 0.6613 is a *correct*-clock rate. It counts parses, and 4 of 13 comparable hand-read tiles are wrong, so correctness is strictly lower and is not estimated here.
- That any of the three failure modes is fixable, or that a different reader clears 0.90 on this corpus. Failure modes 1 and 2 are properties of THIS sealed route, so the limit is the route's, not proven to be the corpus's.
- Repeatability: one run of one route (B11); EasyOCR CUDA and CPU were not compared on the same frames, and no determinism claim is made.
- That any clip matches its game id, that any of it is usable for training, or that the pod producer would emit what this reader emits.
- The 28 rejected frames were not eye-checked individually; the non-circularity evidence is the 20-tile sheet only.