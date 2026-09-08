# G316 preregistration -- scoreboard game-clock liveness (sealed before any metric)

Spec: `docs/evidence/tracking/specs/G316_spec.md`. Verifier contract:
`docs/evidence/tracking/VERIFIER_CONTRACT.md` (Q1: this seal predates the first metric).
Calibration language only. This row makes NO recall, precision, registration,
tracking-quality or harness-pass claim and licenses no `passed` flip.

## 1. Spec premises that are already FALSE, corrected here (S2 / A9 / Q8)

- **Not 1080p.** The spec's step-2a says "two already-tracked 1080p pod broadcasts".
  Measured by `ffprobe` on the pod: `data/footage_bridge/nba__0022500575_s900.mp4`
  (11,226,659 B) and `nba__0022500594_s7200.mp4` (10,431,940 B) are both
  **640x360**, ~130 s, ~3,900 decodable frames. Every pod broadcast is 640x360.
  The row proceeds on the corpus that exists and reports the true resolution.
- **No OCR engine on the pod.** `easyocr`, `paddleocr`, `pytesseract`,
  `rapidocr_onnxruntime`, `doctr` and `mmocr` are all `ModuleNotFoundError` on the
  pod (`tesseract` binary absent too); `torch 2.8.0+cu128`, `cv2 4.14.0`, `numpy
  2.1.2`, `PIL 11.0.0` are present. So step 2 CANNOT run its reader on the pod.

## 2. Machine split (S1 -- named, with the reason)

- **Step 0 PREMISE -- POD.** `data/tracking/<gid>_s<off>/tracking_data.csv` lives
  only on the pod. One `~/bin/pod_run a12` job, CPU only, no GPU.
- **Step 1 TRACE -- LOCAL.** `src/` is in the checkout. Read-only.
- **Step 2a SAMPLE + CROP -- POD.** Same single job: decode, apply the presence
  rule, write crops to a `.npz` fetched back. CPU/ffmpeg-class work, no GPU.
- **Step 2b READ -- LOCAL.** The declared reader runs on this box because no OCR
  engine is importable on the pod (section 1). Local `easyocr 1.7.2`, `cv2 4.11.0`,
  `torch 2.2.0+cu121`. Nothing is installed on the pod; no pod process is touched.

## 3. Sample design (fixed before the run)

- **Broadcasts (n=2):** `0022500575` and `0022500594` -- the two S314 named. A
  broadcast's pod footage is a set of equal-length (~130 s) segment mp4s under
  `data/footage_bridge/nba__<gid>_s<offset>.mp4`.
- **n = 200 frames per broadcast, 400 total.** Frames are allocated EQUALLY across
  that broadcast's segments (segments are equal duration) and, inside each
  segment, taken EVENLY SPACED over the **decoded** frame sequence
  (`idx = round(j*(n_dec-1)/(k-1))`). No head slice.
- **Decoded, not declared.** `CAP_PROP_FRAME_COUNT` over-reports on these files
  (3,923 declared vs 3,897 decoded on the design clip); the sampler indexes the
  decode, never the header.
- **Held-out design game.** The presence rule below was designed on
  `0022500630_s1500` ONLY -- a third game that appears in NEITHER measured
  broadcast. No measured frame was looked at before this seal.

## 4. Scoreboard-presence rule (DECLARED, deterministic, fixed)

The NBA score bug on this corpus sits **bottom-right**, not in the top strip the
production route reads. Declared box, in frame fractions:

    x in [0.72, 1.00), y in [0.75, 0.98)      # 180 x 82 px at 640x360

Let `W` be the boolean mask `min(B,G,R) >= 200` over that box and `rows` the
per-row mean of `W`. The rule fires iff

    max(rows) >= 0.40

i.e. some single row of the box is at least 40 pct near-white -- the solid white
clock strip. One number, one threshold, no per-frame adaptation.

**Design tally (held-out game `0022500630_s1500`, 40 evenly spaced frames, labelled
BY EYE from a contact sheet before the threshold was chosen):** 29 frames carry a
score bug, 11 do not. The rule agrees on 39/40. Its single error is a false
POSITIVE (frame 3796, a white jersey filling the box, `max(rows)=0.656`). It has
ZERO false negatives on the design set. That direction is deliberate: the rule can
only ADD unreadable frames to the denominator, never prune hard ones (B1).

## 5. Reader (DECLARED)

- `easyocr 1.7.2`, `Reader(["en"], gpu=False)`, `readtext(detail=1,
  paragraph=False)`, tokens kept at `conf >= 0.30` -- the same
  `_OCR_CONF_MIN = 0.30` the production route uses.
- Input: the declared box, upscaled 4x with `cv2.INTER_CUBIC`. No other
  preprocessing, no per-frame tuning.
- Parse: `_parse_scoreboard_text()` **imported verbatim** from
  `src/tracking/scoreboard_ocr.py` (read-only import; that file is not edited).
  A frame counts as a clock parse iff it returns `game_clock_sec > 0`.
- Per-frame confidence recorded = mean EasyOCR token confidence on that frame.

## 6. Hand-check protocol (a DECLARED MODEL CHECK, not a human eye check)

20 frames EVENLY SPACED over the **full 400-frame sample** -- not over accepted
frames only, so a scoreboard the rule missed is visible. Each crop is rendered at
5x into a contact sheet, and the clock is read off the render by the model, then
tabulated against the parsed value. This is stated as a model check, not a human
one, wherever it appears. Agreement = |read - parsed| <= 1 s.

## 7. Bar (byte-identical to the spec; Q3 -- never lowered)

metric = parsed-clock rate = frames yielding an `MM:SS` parse / frames whose
presence rule fired, per broadcast; both denominators printed; zero-parse frames
stay in the denominator.
before = the reproduced premise fill: 0 of N `scoreboard_game_clock` cells on each
of the two named pod games, N printed per game.
bar = **>= 90 pct** parsed-clock rate on scoreboard-present frames, AND all 20
hand-checked frames within 1 s, AND the period contradiction explained with a
`file:line`. A bar found unmeetable is reported CLOSED AT LIMIT, never lowered.
must not move = `src/**` byte-identical (SHA-256 of `src/tracking/scoreboard_ocr.py`
and `src/pipeline/unified_pipeline.py` before and after); every existing
`tracking_data.csv` column and the ledger `passed` field untouched; nothing written
under `data/`.

## 8. Stop conditions

- Premise falsified (non-zero clock fill on either game) -> STOP, memo, FALSIFIED.
- Fewer than 30 of 200 present frames in BOTH broadcasts -> STOP, CLOSED AT LIMIT.

SHA256(prereg, all bytes above this line, LF-normalized) = 3bc7e52d1bbee336ee8ba1d90547721c9cfc26e7cbaacd6ad0ef52d2cb4dfbdd
