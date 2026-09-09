GAP G365 | sport basketball | worktree a4 | log cx_g365_fitter_refinement

**FITTER-PRECISION ROW, PREREQUISITE FOR ANY BROADCAST REGISTRATION (successor to G362 PARTIAL 2026-09-09
decb187d: the sealed known-H recovery gate reads 1.6516 px against the 1.0 px bar, reproduced deterministically;
1.33 / 1.78 / 1.89 px on three more view geometries). G362's diagnostic isolated the mechanism: the winning H is
built from FOUR corner points (two fitted W-family lines x two fitted L-family lines, one
`cv2.getPerspectiveTransform`) with NO joint refinement over the other detected supports; fed EXACT lines the same
corner solve reprojects the 398-point template at 0.000000 px, so the floor is LSD grouping + `cv2.fitLine`
noise amplified by extrapolation, not integer detection and not family binning.** Codex PREPARES, a Claude
finisher MEASURES on synthetic fixtures only (no broadcast frame in this row). `src/`, `kernel/`, `api/`,
`intel/` are READ and IMPORT only; the landed `domains/basketball/tracking/line_calibration.py` is READ and
IMPORT only. Build additively in `scripts/platformkit/tracking/g365_*.py`. NEVER write `data/registry/`, never flip
a flag, never move the G362 / G352 bars, never touch the register.

**WHERE THIS ROW RUNS:** ON THE POD, in `/workspace/wt/a4` (`python3 -m` from the worktree root; CPU only,
`nice -n 19 OMP_NUM_THREADS=2`; synthetic fixtures from `g362_synth.py` and the G362 fixture geometries).

**PREMISE (step 0, BINDING before-condition):** re-run G362's `known-h` on its four sealed geometries under the
ARCHIVED fitter and PRINT the gaps (expect 1.65 / 1.33 / 1.78 / 1.89 px). **If every geometry already recovers
<= 1.0 px, the premise is FALSE: STOP, memo, commit, report PREMISE FALSE.**

METHOD (sealed before any number):
  1. **REFINEMENT (additive, `g365_refine.py`):** start from the 4-corner H; then a joint least-squares refinement
     of the 8 homography parameters over ALL FIT-partition support points (G362's FIT strokes, fixed density),
     minimising the symmetric (forward + inverse) point-to-line reprojection residual with a robust loss (Huber,
     sealed delta in px) and a sealed iteration cap; deterministic; the VALIDATION strokes are never touched by
     the refinement (B8) and still make the single accept/refuse decision through G362's validator.
  2. **CONTROLS:** (a) exact-line input must reproduce 0.000 px (unchanged); (b) sub-pixel Gaussian noise sweep
     on the synthetic line endpoints (sigma 0.25 / 0.5 / 1.0 px, sealed seeds, >= 30 draws each) reporting the
     recovery gap for the 4-corner solve vs the refined solve; (c) the four G362 geometries.
  3. **BAR (preregistered):** refined recovery <= 1.0 px on ALL four G362 geometries AND median <= 1.0 px at
     sigma = 0.5 px over >= 30 draws; the 4-corner baseline is reported beside it; a refinement that WORSENS any
     geometry is a REJECT of the candidate refinement, not of the row.
  4. **HAND-OFF:** if the bar holds, write the PROPOSED one-line wiring for G362's `g362_fit_validate.py` (a
     research note, sha256 in the memo); no src hook; no flag. CHANGE NOTHING ELSE.

ACCEPTANCE RULE:
  metric        = recovery gap (px at 720p, median over draws) for baseline vs refined, per geometry and per sigma
  before        = 4-corner solve: 1.6516 / 1.33 / 1.78 / 1.89 px (G362 known_h.json)
  bar           = refined <= 1.0 px on all 4 geometries; median <= 1.0 px at sigma 0.5 over >= 30 draws; exact
                  input stays 0.000; no geometry worsens; 0 bars moved; 0 src edits
  n             = 4 geometries x 3 sigmas x >= 30 draws (sampled, sealed seeds) + the exact control (CONSTRUCT)
  eye check     = REQUIRED: 8 renders (per geometry: baseline vs refined overlay of template on synthetic frame)
  must not move = the G362 validator and bars, `line_calibration.py`, `src/`, every flag, `data/registry/`
  verdict       = **DONE** / **PARTIAL** (name the geometry or sigma that fails) / **PREMISE FALSE**
EVIDENCE: `docs/evidence/tracking/g365_fitter_refinement_2026-09-09.md` (<= 60 lines; VERDICT line 1; NOT VERIFIED;
wall time; SHA-256s) + `.../g365_fitter_refinement_2026-09-09/recovery.csv`, `sweep.csv`, `renders/`, `summary.json`.
**ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT.**
TEST: `tests/platformkit/test_g365_fitter_refinement.py` alone (exact input 0.000 px before and after refinement;
a noisy synthetic case improves; validation strokes are untouched by the refinement; the seal check). **NEVER a
full pytest.** Every new file <= 300 lines.
DIVISION OF LABOUR: codex prepares the prereg (sealed alone: loss, delta, iteration cap, seeds, sigmas, draws, bar),
`g365_refine.py`, the sweep runner, the test and the memo skeleton, exits `agent: PREPARED FOR FINISHER` with
`python3 -m` commands; the Claude finisher runs the premise, the sweep and the renders and scores (Q1). Vocabulary
follows contract Q6; automated scan required. COMMIT: explicit pathspec only; prereg sealed as its OWN commit first
(`SEAL sha256 <hex>`). ASCII stdout. **NEVER PARK.**

VERSION 2026-09-09
