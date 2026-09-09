GAP G367 | sport basketball | worktree a10 | log cx_g367_init_symmetry

**INITIALISATION ROW, SUCCESSOR TO G365 (CLOSED AT LIMIT 2026-09-09 31ac311b: joint refinement with template-guided
re-association brings three synthetic geometries from 1.65 / 2.02 / 1.80 px to 1.13 / 1.12 / 0.76 px, still above
the 1.0 px bar on two, and the fourth (G2_WIDE) is an INIT_FAIL because the court markings are mirror-symmetric
(x -> 50 - x): the 4-corner winner sits 469 px from the labelled truth but 1.92 px from the truth composed with the
mirror; conditioning was refuted -- G2 has the lowest condition number of the four). Codex PREPARES, a Claude
finisher MEASURES on synthetic fixtures; broadcast frames enter ONLY in step 4 as a labelled orientation set.**
`src/`, `kernel/`, `api/`, `intel/` and `domains/basketball/tracking/line_calibration.py` are READ and IMPORT
only. Build additively in `scripts/platformkit/tracking/g367_*.py`. NEVER write `data/registry/`, never flip a
flag, never move the G362 / G365 bars, never touch the register.

**WHERE THIS ROW RUNS:** ON THE POD, in `/workspace/wt/a15` (`python3 -m` from the worktree root; CPU only,
`nice -n 19 OMP_NUM_THREADS=2`; fixtures from `g362_synth.py` and the four G365 geometries; step 4's frames come
from sections pinned by YouTube id + offset + sha256 per G361, fetched with `/workspace/YTDLP_RECIPE.txt`).

**PREMISE (step 0, BINDING before-condition):** on the four G365 geometries, PRINT the recovery gap of the
4-corner winner against the labelled truth AND against every element of the court symmetry group
(identity, mirror x -> 50 - x, the 180-degree rotation, and their composition). **If the minimum over the group
already meets <= 1.0 px on all four with candidate B, the premise is FALSE for the geometry part: STOP that part
and report; the orientation part (step 4) still runs.**

METHOD (sealed before any number):
  1. **SYMMETRY-AWARE SCORING (additive):** `recovery_modulo_symmetry` = min over the sealed symmetry group of
     the reprojection gap; every table reports BOTH the labelled gap and the modulo gap plus the group element
     that attains it. No fixture label is changed.
  2. **INITIALISATION SEARCH (additive to the 4-corner solve):** enumerate the 4-corner candidates over the
     top-K W-family x L-family line pairings (sealed K) AND their symmetry images, score each by the sealed
     whole-template objective from G352/G362 (never a self-fit residual), refine the top-M with G365 candidate B,
     and return the best by modulo gap with its runner-up margin; a sealed ambiguity band on that margin yields
     AMBIGUOUS (never VALID).
  3. **BAR (preregistered, geometry):** modulo gap <= 1.0 px on all four geometries after refinement; the exact
     control stays 0.000; no geometry worsens vs G365 candidate B; the noise sweep (sigma 0.25 / 0.5 / 1.0,
     >= 30 sealed draws) reports modulo medians beside the labelled ones.
  4. **ORIENTATION CUE (broadcast, small, labelled):** the mirror ambiguity is real on a court; the row measures
     whether a SEALED cue resolves it: >= 60 frames from >= 20 sections / >= 8 games (even sample, pinned),
     blind-labelled by terra + sol for "offence attacks left / right / unknown" from the frame + a 3-frame strip
     (no cue value on the sheet), adjudicated; the cue candidates (sealed list, e.g. scoreboard/graphic side,
     bench side, basket visibility, previous-frame continuity) are scored as precision on the labelled set with
     Wilson 95 pct; the best cue is reported, not wired.
  5. CHANGE NOTHING ELSE; no src hook; no flag.

ACCEPTANCE RULE:
  metric        = labelled gap AND modulo gap per geometry (baseline / B / search+B); runner-up margins; sweep
                  medians; orientation-cue precision with intervals; kappa
  before        = G365: G1 1.1287 / G3 1.1165 / G4 0.7636 / G2 INIT_FAIL (labelled); modulo gaps unmeasured
  bar           = modulo gap <= 1.0 px on all four after search + refinement; exact 0.000; no worsening vs B;
                  >= 60 orientation frames rated with n >= 30 per class or PARTIAL; 0 bars moved; 0 src edits
  n             = 4 geometries x 3 sigmas x >= 30 draws; >= 60 orientation frames; 2 raters + adjudication
  eye check     = REQUIRED: 8 synthetic overlays (labelled vs modulo winner) + 10 orientation sheets <= 200 KB
  must not move = the G362 validator and bars, G365's candidate B, `line_calibration.py`, `src/`, every flag
  verdict       = **DONE** / **PARTIAL** (name the geometry, clause or class) / **PREMISE FALSE** (geometry part)
EVIDENCE: `docs/evidence/tracking/g367_init_symmetry_2026-09-09.md` (<= 60 lines; VERDICT line 1; NOT VERIFIED;
wall time; SHA-256s) + `.../g367_init_symmetry_2026-09-09/recovery.csv`, `search.csv`, `sweep.csv`,
`orientation.csv`, `ratings.csv`, `renders/`, `sheets/`, `summary.json`. **ADD ONE RESULTS_LEDGER.md ROW IN THE
SAME COMMIT.**
TEST: `tests/platformkit/test_g367_init_symmetry.py` alone (the modulo gap is 0 for a mirrored exact solution; the
search returns AMBIGUOUS inside the sealed margin band; the sheet builder writes no cue value; the seal check).
**NEVER a full pytest.** Every new file <= 300 lines.
DIVISION OF LABOUR: codex prepares the prereg (sealed alone: symmetry group, K, M, objective, ambiguity band,
sigmas, seeds, cue list, label set, bars), the modules, the test and the memo skeleton, exits `agent: PREPARED FOR
FINISHER` with `python3 -m` commands; the Claude finisher runs the premise, the search, the sweep, pins and rates
the orientation set (blind raters) and scores (Q1). Vocabulary follows contract Q6; automated scan required.
COMMIT: explicit pathspec only; prereg sealed as its OWN commit first (`SEAL sha256 <hex>`). ASCII stdout.
**NEVER PARK.**

VERSION 2026-09-09
