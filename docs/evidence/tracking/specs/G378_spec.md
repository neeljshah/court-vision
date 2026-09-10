GAP G378 | sport basketball | worktree a18 | log cx_g378_orientation_cue

**INDEPENDENT ORIENTATION-CUE ROW, SUCCESSOR TO G371 (DONE 2026-09-10 653da1799: the truth-free selector emits NO_DISTINCT_RUNNER_UP
on 357/360 cells and 0 ACCEPT because every candidate lies in ONE symmetry class -- lines alone cannot disambiguate court mirror
symmetry; orientation_status UNKNOWN 4/4) and to G367 (orientation reference left 12 / right 16 / unknown 26, kappa 0.824485; the 28
resolved attack-direction labels cannot meet two >= 30-per-class quotas and attack direction alone cannot orient absolute court
coordinates).** A Claude finisher PREPARES (prereg sealed alone) and MEASURES on the pod; blind anchor raters (terra + sol) on the PC.
`src/`, `kernel/`, `api/`, `intel/`, `domains/basketball/tracking/line_calibration.py` READ and IMPORT only. Build additively in
`scripts/platformkit/tracking/g378_*.py` (import g371_symmetry_margin / g367_symmetry / g367_orient; copy none). NEVER write
`data/registry/`, never flip a flag, never move a G362 / G365 / G371 bar, never change G371's refusal or margin semantics, never
touch the register.

**WHERE THIS ROW RUNS:** ON THE POD, `/workspace/wt/a18` (`python3 -m`; CPU for decode + cue, <= 6 cores, threads = 1; GPU only if a
frozen detector/OCR is the sealed cue, one job at a time, free VRAM read first); sources = fresh sections whose bytes still exist in
`/workspace/data/footage_corpus` (pin per G361 at decode time: video id + offset + sha256; the corpus is pruned after 90 min when the
volume exceeds 35 GB, so pin and decode IMMEDIATELY after selection); quota: scratch < 1.5 GB, never write under `/workspace/data`.

**PREMISE (step 0, BINDING before-condition):** re-read G371's summary.json / sweep.csv and PRINT the status counts (expect 357 / 2 / 1
/ 0) and orientation_status UNKNOWN 4/4; re-read G367's adjudicated orientation reference (12 / 16 / 26). **If any G371 cell shows
ACCEPT or orientation_status != UNKNOWN, the premise is FALSE: STOP, memo, commit, report.**

METHOD (sealed before any rating):
  1. **THE CUE (sealed, ONE):** an asymmetric broadcast landmark that maps to a court side independently of line fitting -- the sealed
     candidate is the scoreboard/score-bug text side + the bench/table side as read by the deployed OCR route (EasyOCR) on 12 evenly
     spaced interior ticks per section; the cue emits LEFT / RIGHT / UNKNOWN for the basket the home team attacks in the section's first
     half, with a confidence; any missing evidence is UNKNOWN (B3).
  2. **ANCHOR REFERENCE (blind):** >= 120 unique native frames from >= 20 sections / >= 8 games sampled EVENLY (never a head slice);
     raters terra + sol label the court side of an asymmetric anchor (scorer's table side; the visible team bench; the score-bug home
     team position) with NO cue output shown; disagreements adjudicated blind; kappa; UNKNOWN retained.
  3. **SCORING:** per frame, cue vs reference: correct / wrong / UNKNOWN; resolved predictions per class; Wilson 95 pct lower bound per
     class; the symmetry-orbit choice each cue implies for the four G371 geometries and whether it would PICK a class where G371 refused
     (reported as a diagnostic; G371's refusal stands unchanged).
  4. **CONTROLS:** a mirrored copy of 30 frames flips the cue output 30/30; a frame with the score bug masked yields UNKNOWN 30/30.
  5. CHANGE NOTHING ELSE; no src hook; no flag; no G371 re-scoring.

ACCEPTANCE RULE:
  metric        = resolved / all decoded frames; per-class correct share with Wilson 95 pct lower bound; UNKNOWN share; controls; kappa
  before        = G371: orientation UNKNOWN 4/4, 0 accepts; G367: 28 resolved direction labels, quotas unmet
  bar           = >= 120 frames / >= 20 sections / >= 8 games; >= 30 resolved predictions per class AND Wilson lower >= 0.90 per class;
                  controls 30/30 and 30/30; kappa reported; 0 G371 semantics moved (30 perfect predictions alone do not clear 0.90)
  n             = >= 120 frames (SAMPLED, even); 2 raters + adjudication; >= 30 per scored class else PARTIAL
  eye check     = REQUIRED: 30 evenly spaced renders incl. every UNKNOWN and every wrong case
  must not move = G371 refusal/margin semantics, the validator, G362 / G365 bars, the deployed OCR route and weights, every flag
  verdict       = **DONE** / **PARTIAL** (name the class or control) / **PREMISE FALSE**
EVIDENCE: `docs/evidence/tracking/g378_orientation_cue_2026-09-10.md` (<= 60 lines; VERDICT line 1; NOT VERIFIED; wall time;
SHA-256s) + `.../g378_orientation_cue_2026-09-10/{frames.csv,anchors.csv,ratings.csv,reference.csv,cue_predictions.csv,
orbit_choices.csv,controls.csv,summary.json,sheets/,renders/}`. **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT.**
TEST: `tests/platformkit/test_g378_orientation_cue.py` alone (mirror control flips; masked control yields UNKNOWN; even sampler never
a head slice; the seal). **NEVER a full pytest.** Every new file <= 300 lines. Vocabulary follows contract Q6; automated scan required.
Prereg sealed as its OWN commit first (`SEAL sha256 <hex>`). ASCII stdout. **NEVER PARK.**

VERSION 2026-09-10
