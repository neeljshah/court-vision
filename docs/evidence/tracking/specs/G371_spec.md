GAP G371 | sport basketball | worktree a10 | log cx_g371_symmetry_margin

**SELECTOR-REPAIR ROW, SUCCESSOR TO G367 PHASE 1 (2026-09-09 193b3633 / 960d2ca5: the initialisation search reaches
0.72 / 0.76 / 1.13 / 1.07 px MODULO the court symmetry group on the four sealed geometries, but the sealed winner rule
"best by modulo gap" CONSULTS THE LABELLED TRUTH -- an oracle diagnostic, not a selector -- and every winner is
AMBIGUOUS because all refined candidates share one symmetry class, so the margin rule can never separate them).
Astra day review 2026-09-09 section 3. Codex PREPARES, a Claude finisher MEASURES; SYNTHETIC ONLY, CPU only.**
`src/`, `kernel/`, `api/`, `intel/` and `domains/basketball/tracking/line_calibration.py` are READ and IMPORT only.
Build additively in `scripts/platformkit/tracking/g371_*.py` (import G362 / G365 / G367 modules; copy none). NEVER
write `data/registry/`, never flip a flag, never move the G362 / G365 / G367 bars, never touch the register.

**WHERE THIS ROW RUNS:** in the assigned worktree (PC `nba-track-aN` while the pod is down, `/workspace/wt/aN` on
the pod), `python -m` from the worktree root, `OMP_NUM_THREADS=2`, no GPU, no broadcast frame, no section fetch.

**PREMISE (step 0, BINDING before-condition):** re-run G367's `search` on its four sealed geometries and PRINT, per
geometry, (a) whether selection consulted the truth homography (read `g367_search.py`, cite file:line), (b) the
symmetry class of every refined candidate, (c) the runner-up margin as emitted. **If selection is already truth-free
AND distinct-class runners-up exist on >= 3 of 4 geometries, the premise is FALSE: STOP, memo, commit, report.**

METHOD (sealed before any number):
  1. **QUOTIENT BY SYMMETRY:** cluster candidate homographies into equivalence classes by their projections of a
     sealed fixed-density template (tolerance sealed in px at 720p); one representative per class.
  2. **TRUTH-FREE SELECTION:** rank class representatives by a FIT-only objective J (the G352/G362 whole-template
     objective over FIT strokes; VALIDATION strokes and the truth H never enter); winner = best J; runner-up = best
     DISTINCT class; margin = (J2 - J1) / max(|J2|, epsilon) with sealed epsilon; ACCEPT at margin >= 0.10 only
     together with the absolute fit bar and the G362 held-out validation decision; if no distinct class exists emit
     `NO_DISTINCT_RUNNER_UP` (never an infinite margin, never a pass); report `geometry_status` and
     `orientation_status` SEPARATELY (orientation stays UNKNOWN from lines alone).
  3. **EVALUATION ONLY THEN:** the truth H is used only to score the selected winner (labelled gap AND modulo gap),
     never to choose it; archive every candidate class, J, margin and outcome (including refusals).
  4. **CONTROLS:** exact-line input recovers 0.000 px; duplicate / permutation invariance (shuffled candidate order
     and cloned candidates change nothing); >= 30 PLANTED ambiguous distinct-class cases (a second class with J
     within the band) must be REFUSED at >= 0.95; the four G367 geometries x sigma {0.25, 0.5, 1.0} x 30 sealed
     draws.
  5. **SENSITIVITY (uncertainty, not accuracy):** perturb the FIT supports under sealed noise and map probe feet
     across the whole visible court; report mapped-foot error median / p95 in metres per geometry against the
     proposed budgets median <= 0.25 m, p95 <= 0.50 m (labels above budget are uncertainty-masked).
  6. CHANGE NOTHING ELSE; no src hook; no flag.

ACCEPTANCE RULE:
  metric        = truth-free winner gap (labelled and modulo) per geometry; margin / status per geometry; planted
                  ambiguity refusal share; invariance checks; sensitivity table (m)
  before        = G367: oracle winners 0.72 / 0.76 / 1.13 / 1.07 px, all AMBIGUOUS, margin none
  bar           = 0 truth or VALIDATION access during selection (asserted by a test that swaps the truth and sees
                  identical selection); exact control 0.000; invariance exact; planted ambiguity refused >= 0.95;
                  the truth-free winner gap reported for all four (no px bar is claimed here -- the 1.0 px bars stay
                  failed where they fail); sensitivity budgets reported met / unmet per geometry
  n             = 4 geometries x 3 sigmas x 30 draws; >= 30 planted cases (sealed seeds)
  eye check     = REQUIRED: 30 evenly spaced synthetic overlays (winner vs truth vs runner-up class) <= 200 KB
  must not move = the G362 validator and bars, G365 candidate B, G367's sealed search, `line_calibration.py`, flags
  verdict       = **DONE** / **PARTIAL** (name the clause) / **PREMISE FALSE**
EVIDENCE: `docs/evidence/tracking/g371_symmetry_margin_2026-09-09.md` (<= 60 lines; VERDICT line 1; NOT VERIFIED;
wall time; SHA-256s) + `.../g371_symmetry_margin_2026-09-09/fixtures.json`, `candidates.csv`, `selected.csv`,
`ambiguity_controls.csv`, `sensitivity.csv`, `renders/`, `summary.json`. **ADD ONE RESULTS_LEDGER.md ROW IN THE
SAME COMMIT.**
TEST: `tests/platformkit/test_g371_symmetry_margin.py` alone (truth swap leaves selection unchanged; cloned
candidates leave the margin unchanged; a planted distinct class inside the band is refused; exact control 0.000;
the seal check). **NEVER a full pytest.** Every new file <= 300 lines.
DIVISION OF LABOUR: codex prepares the prereg (sealed alone: class tolerance, J, epsilon, margin, band, seeds,
budgets), the modules, the test and the memo skeleton, exits `agent: PREPARED FOR FINISHER` with `python -m`
commands; the Claude finisher runs the premise, the sweep, the plants, the sensitivity and scores (Q1). Vocabulary
follows contract Q6; automated scan required. COMMIT: explicit pathspec only; prereg sealed as its OWN commit
first (`SEAL sha256 <hex>`). ASCII stdout. **NEVER PARK.**

VERSION 2026-09-09
