# G316 -- scoreboard game-clock liveness, 2026-09-07

**VERDICT: REJECT, self-reported under the spec's NON-TAUTOLOGY clause.** The sealed presence rule does not transfer off the broadcast it was designed on, so the acceptance metric's denominator is invalid and its rate estimates nothing. **NOT closed at limit:** 8 of 20 evenly-spaced renders visibly carry a game clock, so the low present-counts are the rule's failure, not the corpus's. No bar lowered (Q3). Calibration language only; no recall/precision/registration/tracking-quality/harness-pass claim, no `passed` flip, nothing adopted, nothing deployed. Prereg sealed before any metric: `g316_preregistration_2026-09-07.md`, SHA-256 `3bc7e52d1bbee336ee8ba1d90547721c9cfc26e7cbaacd6ad0ef52d2cb4dfbdd`, commit `67827cf54` (Q1).

## Premise (step 0) -- REPRODUCED, not falsified
Pod, `data/tracking/<gid>_s<off>/tracking_data.csv`, all segments per game.

| game | seg CSVs | N rows | `scoreboard_game_clock` filled | `scoreboard_period` filled | distinct periods | clip sec |
|---|---|---|---|---|---|---|
| 0022500575 | 11 | 42,133 | **0** | 38,817 (92.1 pct) | 1, 2, 3, 4 | 1,424.12 |
| 0022500594 | 15 | 37,391 | **0** | 37,381 (99.97 pct) | 1, 2, 3, 4 | 1,747.90 |

Segment `0022500575_s1500` alone: 6,066 rows, 0 clock, 6,066 period (100 pct), `source_duration` **155.22 s** -- periods 1-4 inside one 155 s clip, the S314 contradiction at segment grain.

## Period contradiction -- EXPLAINED (the deliverable)
`src/pipeline/unified_pipeline.py:4282-4350` `_backfill_scoreboard_period()`, called at `:3001`, fills every empty cell with `q = max(1, min(4, int(frame / max_frame * 4) + 1))` (`:4335-4340`). `q` depends only on the row's position in the file, so it emits 1/2/3/4 across a clip of any length. **That fallback, not a scoreboard reading, is what puts periods 1-4 inside a 152 s clip.** Counts are unequal (575: 7,650/10,092/10,288/10,787) because rows-per-frame varies, as the percentile mechanism predicts. PROPOSED diff, not applied: `docs/research/organization-sprint/PROPOSED-scoreboard-period-no-frame-percentile-fill-2026-09-07.md` -- present in worktree a12 but NOT committed, because `docs/research/` is gitignored local-only by project rule.

Two measured reasons the cells are empty upstream:
1. **No OCR engine in the pod producer env.** `easyocr`, `paddleocr`, `pytesseract`, `rapidocr_onnxruntime`, `doctr`, `mmocr` all `ModuleNotFoundError`; no `tesseract` binary. `_get_reader()` (`src/tracking/scoreboard_ocr.py:141-175`) raises, `_ocr_frame`'s `except Exception` (`:308-310`) swallows it and returns `_DEFAULT_STATE` (`:121-134`, `game_clock_sec: -1.0`), and the write site (`src/pipeline/unified_pipeline.py:2751-2768`) emits `""` on every row. 0/N is mechanical.
2. **Wrong scan region.** `_TOP_FRAC = 0.10` (`src/tracking/scoreboard_ocr.py:118`) reads the top 10 pct; the score bug on these broadcasts is bottom-right.

## Sources actually opened (A9) -- NOT 1080p
Every pod broadcast is **640x360**, not the 1080p the spec asserted; corrected in the prereg before the run. Sampled: `data/footage_bridge/nba__0022500575_s{6600,7200,8700,900}.mp4` (11,563,774 / 11,449,336 / 11,589,720 / 11,226,659 B, 3,897 decoded frames each) and `nba__0022500594_s{7200,8700,9900}.mp4` (10,431,940 / 11,233,132 / 10,702,247 B, 3,901 each). The corpus is LIVE -- 0022500575 had 6 such files 20 min before the run and 4 at run time.

## Measurement (n = 400: 200 per broadcast, evenly spaced over decoded frames, no head slice)

| broadcast | sampled | rule fired | rule rejected | parsed clock | rate | median conf |
|---|---|---|---|---|---|---|
| 0022500575 | 200 | 20 | 180 | 0 | **0.000** | 0.747 |
| 0022500594 | 200 | 8 | 192 | 2 | **0.250** | 0.833 |

Bar >= 0.90; both fail. Both denominators are invalid -- see next section.
## The 20-render check (evenly spaced over the FULL 400, not over accepted frames)
- **8 of 20 tiles carry a legible game clock** (tiles 10-15, 17, 19, all in 0022500594 segments): `3RD 2:57`, `3RD 2:57`, `3RD 2:32`, `4TH 4:27`, `4TH 4:15`, `4TH 3:34`, `4TH :06.6`, `4TH :03.1`.
- **The rule rejected all 8** (`presence_stat` 0.100-0.311 against its 0.40 bar). Its only 2 acceptances in the set (tiles 1, 2) are an ad banner and a stat card, neither a scoreboard. Agreement 10/20; 8 false negatives on every clock-bearing frame; 2 false positives.
- Cause: the sealed statistic is "some row of the box is >= 40 pct near-white", designed on a broadcast whose clock strip is solid white. These broadcasts use a dark-navy bug with white text, which has no near-white row. The rule is broadcast-skin-specific.
- So the 0.000 / 0.250 above are computed over the wrong frames and are reported as invalid, not as a readability result.
- Independent second parser gap seen in the renders: under one minute the clock renders `:06.6` / `:03.1`, which `_parse_scoreboard_text`'s `\b(\d{1,2})[:.](\d{2})\b` cannot match.

## Corpus-integrity observation (flagged, not claimed)
The 0022500594 renders show one internally consistent Phoenix-Detroit game (79-81 -> 80-81 -> 96-100 -> 98-102 -> 102-107 -> 105-107, 3RD -> 4TH); the 0022500575 renders show Paycom Center / OKC promos and a Spurs stat card. **Whether either matches its NBA game id is NOT VERIFIED here** -- promos and highlight inserts appear inside any broadcast. S314 proposed staging exactly these two as teacher broadcasts, so this deserves its own row.

## Named fix pass (why REJECT, not CLOSED AT LIMIT)
Re-seal a fresh prereg whose presence rule is designed across >= 3 broadcast skins (at minimum a white-strip bug and a dark bug) and validated on a held-out skin before scoring, then re-run. Choosing a new rule now, after seeing this outcome, is exactly the B1 circularity the spec forbids, so no rule was changed and no number rescued.

## Must not move -- verified
`src/tracking/scoreboard_ocr.py` SHA-256 `63ddfd4a05bbac177a4264bb97a232013fbb959184f2f3833bc847efdd6182e4` and `src/pipeline/unified_pipeline.py` `bb92310f54c06ffa4c7caf6bea23861a29c35f3588b6fb4a375aeaf74b6b15f8`, identical before and after; `git status src/` clean. No `tracking_data.csv` column renamed or removed, no ledger `passed` touched, no threshold changed, nothing written under `data/`, nothing copied to the pod, no pod process signalled. Pod CONTEXT `du -sm /workspace` = 24,602 MB. Pod log tail: `POD_RUN_DONE job=20260907184548_223699_7371 rc=0`.

## Tests
- `python -m pytest tests/platformkit/test_g316_scoreboard_clock_liveness.py -q -p no:cacheprovider` -> **3 passed**, 29.19 s, no skips (real EasyOCR ran). Asserts: the presence rule fires on a drawn scoreboard and not on a frame without one; the parsed clock equals the drawn `5:14` (314.0 s); an absent frame stays in the sampled denominator and out of the numerator; the full additive column set is preserved.
- `python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider` -> **1 passed** (A12; the new module is 285 lines, under the 300 cap, so no allowlist entry was needed).

## Artifacts
`docs/evidence/tracking/g316/`: `g316_premise.json`, `g316_sample_summary.json`, `g316_liveness_summary.json`, `g316_frame_records.jsonl` (400 additive per-frame records, full column set), `g316_handcheck_index.json`. Renders and crops stay local under `scripts/platformkit/tracking/out_g316/` (`g316_handcheck_sheet.png`, `g316_crops.npz`). Module: `scripts/platformkit/tracking/g316_scoreboard_clock_liveness.py` -- the only file that would be deployed if a verifier accepts; none was copied to the pod (B5).

## NOT VERIFIED
- Any parsed-clock rate for either broadcast; 0.000 / 0.250 are over an invalid denominator and estimate nothing.
- Whether a correct presence rule clears 90 pct at 640x360, or whether the clock is machine-readable at this resolution at all. The renders show it is *eye*-readable; that is a different claim.
- That either broadcast matches its NBA game id, or that either is usable for training; and that the local reader reproduces what the pod producer would emit (the pod cannot run one).
- Repeatability -- one run of one route (B11), no determinism claim; and whether removing the period back-fill breaks its downstream readers, which was not surveyed.
