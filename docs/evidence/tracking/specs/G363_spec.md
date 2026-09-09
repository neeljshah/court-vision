GAP G363 | sport basketball | worktree a7 | log cx_g363_ball_coverage

**BALL-DETECTION ROW ON THE G335 LINE (astra plan 2026-09-09, item 6: coverage x3 under a precision constraint).
Codex PREPARES the experiment harness, a Claude finisher RUNS the GPU arms on the pod, blind model raters build
the reference.** `src/`, `kernel/`, `api/`, `intel/` are READ and IMPORT only (the detector is CALLED, never
edited). Build additively in `scripts/platformkit/tracking/g363_*.py`. NEVER write `data/registry/`, never flip a
flag, never move the G344 thresholds or the G357 ownership radius, never touch the register.

**WHERE THIS ROW RUNS:** ON THE POD, in `/workspace/wt/a7` (`python3 -m` from the worktree root; one RTX 3090 --
run arms SEQUENTIALLY after measuring free VRAM; decode each reference frame ONCE into a cache with
OMP/MKL/OpenCV threads = 1 under the 5.1-core quota; report GPU minutes and decoded fps). Frames come from sections
re-fetched with `/workspace/YTDLP_RECIPE.txt`; identity per G361 (UNKNOWN alignment => the frame is a NEW frame with
its own hash, never joined to an archived table by frame number).

**WHY THIS ROW EXISTS.** After the G354 pixel fix, ball detection covers ~0.18 of frames (G357 survival.csv) and
px-joined ownership is 3 of 1,800: detection coverage is the ceiling for every ball-derived feature. Coverage can
be faked by lowering thresholds, so the metric must carry a precision constraint measured on frames the detector
never tuned on.

**PREMISE (step 0, BINDING before-condition):** re-measure baseline coverage C0 = observed detections / all frames
on the SEALED reference set (below) with the deployed detector at its deployed settings, and print the G357
survival.csv figure beside it. **If C0 >= 0.50 the premise is FALSE: STOP, memo, commit, report PREMISE FALSE.**
If C0 = 0, x3 is undefined: report the LIMIT.

METHOD (sealed before any arm runs):
  1. **REFERENCE (blind, game-disjoint from development):** >= 600 native frames sampled EVENLY (random start,
     fixed spacing; never a head slice) across >= 30 sections / >= 10 games / 2 competitions, each with a short
     3-frame strip; raters terra and sol label VISIBLE / ABSENT / UNKNOWN plus a ball centre (and box when
     visible) with NO candidate, score or arm shown; disagreements adjudicated blind by the delegate; kappa
     reported; UNKNOWN retained in the full-frame denominator with its share printed.
  2. **DEVELOPMENT ARMS (<= 8, sealed list, on development games only):** confidence {0.05, 0.10, 0.25} at the
     deployed input; input {640, 960}; 2x2 tiling at 640 with 20 pct overlap (dedupe in crop coordinates); causal
     3-tick temporal NMS resetting at cuts (history = INFERRED, never an observed TP); one small fine-tune (frozen
     backbone, last layers, <= 10 epochs) ONLY if >= 500 audited observed boxes from >= 5 development games exist,
     else LIMIT and skip. Select ONE winner on development precision-constrained coverage; then ONE held-out run.
  3. **MATCHING:** one-to-one, observed centre within max(3 px, half the reference diameter), distances normalised
     to 720p; every unmatched or duplicate output is FP; predictions on UNKNOWN frames count as FP.
  4. Archive all predictions, the decode cache manifest (frame sha256), per-game paired scores, cluster intervals.
  5. CHANGE NOTHING ELSE; no production hook; no flag.

ACCEPTANCE RULE:
  metric        = C = TP / N over ALL sealed reference frames (N includes ABSENT and UNKNOWN); Wilson 95 pct
                  precision; FP / N_absent; TP / N_visible; abstention; per-game paired deltas
  before        = C0 (measured here) with the G357 figure (~0.18) beside it
  bar           = C1 >= 3 x C0 AND Wilson lower precision bound >= 0.90 AND FP / N_absent <= 0.01 on the held-out
                  reference; >= 150 VISIBLE and >= 150 ABSENT references, else PARTIAL
  n             = >= 600 frames / >= 30 sections / >= 10 games / 2 competitions; 2 raters + adjudication
  eye check     = REQUIRED: 30 evenly spaced native frames with both blind ratings and the winner's output
  must not move = G344 thresholds, G357 radius, the deployed detector weights and settings, every flag, the
                  daemon, `data/registry/`
  verdict       = **DONE** / **PARTIAL** / **LIMIT** (C0 = 0 or < 500 boxes) / **PREMISE FALSE** with the numbers
EVIDENCE: `docs/evidence/tracking/g363_ball_coverage_2026-09-09.md` (<= 60 lines; VERDICT line 1; NOT VERIFIED;
GPU minutes; SHA-256s) + `.../g363_ball_coverage_2026-09-09/frames.csv`, `ratings.csv`, `frame_scores.csv`,
`predictions.csv`, `arms.csv`, `summary.json`, `sheets/`. **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT.**
TEST: `tests/platformkit/test_g363_ball_coverage.py` alone (one-to-one matching; UNKNOWN-frame prediction counts
FP; even sampler never returns a head slice). **NEVER a full pytest.** Every new file <= 300 lines.
DIVISION OF LABOUR: codex prepares the prereg (sealed alone: sampling rule, arm list, matching rule, bars), the
sampler, the sheet builder, the arm runner, the scorer, the test and the memo skeleton, exits `agent: PREPARED FOR
FINISHER` with `python3 -m` commands; the Claude finisher seals the reference, runs the raters, runs the arms one
at a time and scores (Q1). Vocabulary follows contract Q6; automated scan required. COMMIT: explicit pathspec only;
prereg sealed as its OWN commit first (`SEAL sha256 <hex>`). ASCII stdout. **NEVER PARK.**

VERSION 2026-09-09
