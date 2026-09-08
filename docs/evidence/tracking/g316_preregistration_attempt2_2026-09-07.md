# G316 attempt-2 preregistration -- scoreboard game-clock liveness (sealed before any scoring frame is viewed)

Spec: `docs/evidence/tracking/specs/G316_spec.md` VERSION `2026-09-07b` (amendment
`70252d816`). Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` (Q1: this seal
predates the first metric). Attempt 1 (prereg `67827cf54`, candidate `9287112e5`,
verified REJECT `b3338efbc`) is not re-litigated here; its premise finding and its
period-back-fill trace stand and are cited, not recomputed from scratch.
Calibration language only. This row makes NO recall, precision, registration,
tracking-quality or harness-pass claim and licenses no `passed` flip.

## 1. Premise, re-measured on the clips this attempt scores (Q8, measured before this seal)

Pod, `/workspace/nba-ai-system/data/tracking/<clip>/tracking_data.csv`:

| clip | N rows | `scoreboard_game_clock` filled | `scoreboard_period` filled | distinct periods | clip sec |
|---|---|---|---|---|---|
| 0022400909_s900 | 5,603 | **0** | 5,603 | 1,2,3,4 | 132.53 |
| mil_chi_2025 | 2,642 | **0** | 2,642 | 1,2,3,4 | 906.47 |
| ncaa_basketball_zqBCKovJCQU | 6,623 | **0** | 6,623 | 1,2,3,4 | 965.60 |
| wnba_06 | 3,606 | **0** | 3,606 | 1,2,3,4 | 955.80 |

0 of 18,474 rows, and periods 1-4 inside a 132.53 s clip. Premise REPRODUCED, not
falsified. If any clip had shown a non-zero clock fill the row STOPS as FALSIFIED.

## 2. Sources (A9) -- all >= 720p, all native pod sections

SCORING clips (100 evenly spaced frames each, n = 400):

| id | skin | path under `/workspace/nba-ai-system/data/footage_corpus/` | bytes | WxH | sec |
|---|---|---|---|---|---|
| C1 | NBA national section (feeder v3) | `nba__0022400909_s900.mp4` | 34,795,729 | 1280x720 | 130.162 |
| C2 | NBA regional broadcast | `nba__mil_chi_2025.mp4` | 258,015,436 | 1280x720 | 906.530 |
| C3 | NCAA tournament broadcast | `ncaa_basketball__ncaa_basketball_zqBCKovJCQU.mp4` | 467,936,551 | 1920x1080 | 965.650 |
| C4 | WNBA broadcast | `wnba__wnba_06.mp4` | 430,058,965 | 1920x1080 | 960.033 |

DESIGN clips (40 frames each, n = 160; DISJOINT from the scoring clips, and no
scoring frame was extracted or viewed before this seal):

| id | skin (bug geometry seen on the design sheets) | path | bytes | WxH | sec |
|---|---|---|---|---|---|
| D1 | NBA 2025, bottom-RIGHT box | `nba__den_phx_2025.mp4` | 168,615,531 | 1280x720 | 587.77 |
| D2 | NCAA/CBS, FULL-WIDTH bottom bar | `ncaa_basketball__ncaa_basketball_mRkuGgeECak.mp4` | 487,249,282 | 1920x1080 | 964.52 |
| D3 | WNBA, bottom-CENTRE bar | `wnba__wnba_02.mp4` | 138,654,331 | 1280x720 | 960.31 |
| D4 | amateur LED overlay, bottom-LEFT box | `basketball__g220c_jh3fnwMi7dM.mp4` | 346,739,796 | 1920x1080 | 960.10 |

Design-set frame manifest (per-frame PNG SHA-256): committed as
`docs/evidence/tracking/g316_attempt2/g316_design_manifest.json`.
SHA-256 over the 160 frame hashes, sorted and LF-joined =
`5c81403157dcc4f0d2062d114a54348b125b089cf3350186c84d08aa38ed3c73`.

## 3. Sampling rule (fixed here, applies to design and scoring alike)

Frame j of k from a clip of ffprobe `format=duration` D seconds is taken at
`t_j = D * (j + 0.5) / k` via `ffmpeg -ss t_j -i <file> -frames:v 1`. Evenly spaced
over the WHOLE clip, no head slice (B7), midpoints of k equal bins. Timestamp
indexing, not header frame counts -- attempt 1 measured `CAP_PROP_FRAME_COUNT`
over-reporting on this corpus. k = 100 per scoring clip, k = 40 per design clip.

## 4. Region set (DECLARED, frame fractions, x0,x1,y0,y1)

    R1 TOP      = 0.00, 1.00, 0.00, 0.16
    R2 BOT      = 0.00, 1.00, 0.78, 1.00
    R3 BOTLEFT  = 0.00, 0.55, 0.78, 1.00
    R4 BOTRIGHT = 0.45, 1.00, 0.78, 1.00

R1 supersedes the production route's `_TOP_FRAC = 0.10` scan
(`src/tracking/scoreboard_ocr.py:118`); R2 is kept whole so a bottom-CENTRE bug is
never cut in half by the R3/R4 split; R3 and R4 overlap on purpose and give a
small far-left or far-right bug more pixels after upscaling.

## 5. Presence rule (DESIGNED ON THE DESIGN SET ONLY, SEALED HERE)

For a region R let `white(R)` = max over rows of the fraction of pixels with
`min(B,G,R) >= 200`, and `edge(R)` = max over rows of the fraction of columns with
`|d(gray)/dy| >= 40` (an overlay plate has straight horizontal borders). Both are
one number per region, no per-frame adaptation. The rule is

    scoreboard_present  iff  white(R2) >= 0.04  AND  edge(R2) >= 0.07

**Design tally.** The 160 design frames were labelled BY EYE off contact sheets
(model eye, declared) as carrying / not carrying a broadcast overlay bearing a game
clock: 153 present, 7 absent. The sealed rule agrees on **159 of 160**: 153 of 153
present frames fire (ZERO false negatives on all four skins) and 6 of 7 absent
frames are rejected; its single error is a FALSE POSITIVE (`wnba_02` f010, a pink
stat card with no clock). Per-skin present-minima of the two statistics are
white/edge 0.050/0.090 (D4), 0.077/0.173 (D1), 0.404/0.327 (D2), 0.097/0.189 (D3);
the sealed thresholds 0.04/0.07 sit below every one of them, so the rule has
headroom on each skin rather than a knife-edge fit to the tightest.
The error direction is deliberate: a rule that only over-accepts can add
unreadable frames to the denominator but can never prune hard ones (B1).

## 6. Reader (DECLARED and PINNED)

- Engine: **EasyOCR 1.7.2**, installed ON THE POD into an isolated tree
  `/workspace/ocr_env` with `pip install --target /workspace/ocr_env --no-deps
  easyocr==1.7.2 pyclipper python-bidi`, reached only via `PYTHONPATH`.
  `python3 -c "import cv2;print(cv2.__version__)"` in the daemon's own env is
  `4.14.0` before and after the install. The deployed tree
  `/workspace/nba-ai-system` is not written; no pod process is signalled (B5 note).
- `easyocr.Reader(["en"], gpu=False)`, `readtext(detail=1, paragraph=False)`,
  tokens kept at `conf >= 0.30` -- the same `_OCR_CONF_MIN = 0.30` the production
  route uses (`src/tracking/scoreboard_ocr.py:119`).
- Input per frame: each of R1..R4 upscaled 4x with `cv2.INTER_CUBIC`. No other
  preprocessing, no per-frame tuning. Tokens from the four regions are UNIONED.
- Parse: `_parse_scoreboard_text()` **imported verbatim** from
  `src/tracking/scoreboard_ocr.py` (read-only import; that file is not edited). A
  frame counts as a clock parse iff it returns `game_clock_sec > 0`.
- Per-frame confidence recorded = mean kept-token confidence on that frame.
- KNOWN, DECLARED NON-MATCH: the production regex is
  `\b(\d{1,2})[:.](\d{2})\b`, so a sub-minute display (`:02.8`, `41.2`, `17.9`)
  does not parse. Those frames stay in the denominator as non-parses, and their
  count is reported separately as CONTEXT. The bar is not adjusted for them (Q3).

## 7. Hand-read protocol (a DECLARED MODEL READ, not a human eye check)

20 frames EVENLY SPACED over the FULL 400-frame scoring sample -- not over accepted
frames only, so a scoreboard the rule missed is visible (B7, and the spec's
NON-TAUTOLOGY clause). Each frame's R2 crop is rendered at 5x into a contact sheet
and the clock is read off the render **by the model, declared as a model read**.
The artifact carries, per tile: `hand_read_clock` (the string read, or `null` when
no clock is legible), `hand_read_sec`, `parsed_clock`, `parsed_sec` and
`abs_error_sec = |hand_read_sec - parsed_sec|` (`null` when either side is absent).
Tolerance: agreement iff `abs_error_sec <= 1.0`.

## 8. Bar (byte-identical to the spec; Q3 -- never lowered)

    metric        = parsed-clock rate = frames yielding an MM:SS parse / frames
                    whose scoreboard_present rule fired, per skin and pooled; both
                    denominators printed; zero-parse frames stay in the denominator
    before        = the reproduced premise fill: 0 of N scoreboard_game_clock
                    cells, N printed per clip (section 1)
    bar           = >= 90 pct parsed-clock rate on scoreboard-present frames, AND
                    every one of the 20 hand-read frames within 1 s of the parsed
                    clock, AND the period contradiction explained with a file:line
    n             = 100 sampled frames per clip, 4 clips (n = 400)
    must not move = src/** byte-identical (SHA-256 before and after for
                    src/tracking/scoreboard_ocr.py and
                    src/pipeline/unified_pipeline.py); every existing
                    tracking_data.csv column and the ledger `passed` field
                    untouched; nothing written under data/

Wilson 95 pct intervals are printed beside every rate. A bar found unmeetable is
reported CLOSED AT LIMIT, never lowered.

## 9. Verdict rule (fixed here)

- Pooled parsed-clock rate >= 0.90 AND all 20 hand-read frames within 1 s -> PASS.
- Otherwise -> REJECT or CLOSED AT LIMIT, decided by the NON-TAUTOLOGY test: if the
  20-frame sheet shows legible clocks on frames the presence rule REJECTED, the
  denominator is invalid and the verdict is REJECT with a named fix pass; if the
  rule fired on every legible clock and the reader still missed them, the verdict
  is CLOSED AT LIMIT with the failure mode named.
- Premise falsified on any clip -> STOP, memo, FALSIFIED.
- Fewer than 30 of 100 present frames on EVERY clip -> STOP, CLOSED AT LIMIT.

SHA256(prereg, all bytes above this line, LF-normalized) = 23a01551e94d1ab3cbd8e0ab7655886547a53f762c5acf0ea688d244b0820fc4
