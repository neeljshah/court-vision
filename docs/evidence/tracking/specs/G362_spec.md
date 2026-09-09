GAP G362 | sport basketball | worktree a4 | log cx_g362_registration_refusal

**REGISTRATION ROW, SUCCESSOR TO G334 AND G352 (astra plan 2026-09-09, item 5). Codex PREPARES, a Claude finisher
MEASURES on the pod.** `src/`, `kernel/`, `api/`, `intel/` are READ and IMPORT only. Build additively in
`scripts/platformkit/tracking/g362_*.py` (no production hook). NEVER write `data/registry/`, never flip a flag,
never move a G352 bar or the G342 templates (they stay `template_status=ASSUMED`), never touch the register.

**WHERE THIS ROW RUNS:** ON THE POD, in `/workspace/wt/a4` (`python3 -m` from the worktree root; GPU and cv2 local;
sections re-fetched from YouTube with the feeder recipe in `/workspace/YTDLP_RECIPE.txt`; identity per G361 --
a frame whose source binding is UNKNOWN is UNKNOWN here too, never certified).

**WHY THIS ROW EXISTS.** G334 and G352 measured court registration at 0 of 6 sections under two objectives, and
the fitter reports `valid` on 84 of 84 NON-COURT frames: the current cascade cannot refuse. Every self-fit
residual is B8-contaminated (RANSAC inliers grading their own homography). Nothing downstream (teacher
geometry, court_calibration sidecars) can be trusted until registration can say NO and its validity is judged
on markings it did not fit.

**PREMISE (step 0, BINDING before-condition):** reproduce G352's `metrics.csv` / `fit.reason` on its negative set:
non-court acceptance must still read 84/84 and the positive sections 0/6 under the archived code path. If the
pixels of the 84 frames are gone, re-fetch by G361 identity; if alignment is UNKNOWN, report the replay NOT
VERIFIED and run the fresh negatives only. **If the archived cascade already refuses >= 80 of 84 negatives, the
premise is FALSE: STOP, memo, commit, report PREMISE FALSE.**

METHOD (sealed before any broadcast frame is scored):
  1. **Known-H recovery test first:** synthetic court lines under a known H -> detected-line fit must recover H
     within <= 1 px reprojection at 720p, else PARTIAL before any broadcast work.
  2. **FIT / VALIDATION partition of physical markings:** whole strokes (sidelines, baselines, lane lines, arcs)
     get disjoint stroke ids; >= 25 pct of strokes are RESERVED for VALIDATION with fixed support density and
     stroke digests. FIT alone chooses H, template, search and runner-up ranking; the held-out strokes make ONE
     accept/refuse decision on the frozen winner -- never a refit, never a second candidate.
  3. **Validity bars (preregistered):** >= 2 held-out marking families present; >= 30 held-out support points per
     frame; bidirectional (forward + inverse) median residual <= 8 px at 720p; absent supports => NO_VALIDATION
     (never valid). Missing-evidence states are explicit: NO_LINES, NO_VALIDATION, REFUSED, VALID.
  4. **Negative controls:** the RAW fitter (no presence filter) and the full cascade both face (a) the 84 archived
     negatives if pixels survive and (b) >= 200 fresh blind non-court frames from >= 30 sections (even sample).
  5. **Positives:** >= 6 court sections from >= 4 games x 60 frames each (even sample), all feet counted with
     n >= 100 per section; archive per-point forward/inverse residuals, out-of-frame penalties, H, uncertainty.
  6. CHANGE NOTHING ELSE; no src hook; sidecars only under the row's evidence dir (never `data/`).

ACCEPTANCE RULE:
  metric        = negative accepts / all negatives (raw fitter AND cascade); G352 section bars on positives
  before        = 84/84 negatives accepted; 0/6 positive sections
  bar           = known-H recovery <= 1 px; 0/84 historical accepts (or NOT VERIFIED if pixels are gone) AND
                  0 of >= 200 fresh negative accepts; >= 4 of 6 positive sections meet the archived G352 bars
                  (validH >= 0.50, feet-inside >= 0.60 at n >= 100, forward median <= 8 px) with held-out validity
  n             = >= 6 x 60 positive frames / >= 4 games; >= 200 negatives / >= 30 sections; >= 100 feet per section
  eye check     = REQUIRED: 30 evenly spaced renders (fit strokes vs held-out strokes, refusals shown) <= 200 KB
  must not move = G352 bars, G342 templates, production, every flag, the daemon, `data/registry/`
  verdict       = **DONE** / **PARTIAL** (name the unmet bar) / **PREMISE FALSE** with the counts
EVIDENCE: `docs/evidence/tracking/g362_registration_refusal_2026-09-09.md` (<= 60 lines; VERDICT line 1; NOT
VERIFIED; wall time; SHA-256s) + `.../g362_registration_refusal_2026-09-09/residuals.csv`, `negative_decisions.csv`,
`metrics.csv`, `H.json`, `summary.json`, `renders/`. **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT.**
TEST: `tests/platformkit/test_g362_registration_refusal.py` alone (known-H recovery; a frame with no held-out
strokes returns NO_VALIDATION; a crowd frame is REFUSED). **NEVER a full pytest.** Every new file <= 300 lines.
DIVISION OF LABOUR: codex prepares the prereg (partition rule, bars, negative-control design, even-sampling rule),
the fitter/validator modules, the synthetic test and the memo skeleton, exits `agent: PREPARED FOR FINISHER` with
`python3 -m` commands; the Claude finisher fetches, scores and writes the memo (Q1). Vocabulary follows contract
Q6; automated scan required. COMMIT: explicit pathspec only; prereg sealed as its OWN commit first (`SEAL sha256
<hex>`). ASCII stdout. **NEVER PARK.**

VERSION 2026-09-09
