GAP G350 | sport basketball | worktree aX | log cx_g350_wide_cue_validation

**VIEW-CLASS VALIDATION ROW (astra midday review 2026-09-08, item E; follows the G341 verifier NEW GAP).
Codex PREPARES, a finisher MEASURES; model raters replace human annotation (no human input is available).**
`src/`, `kernel/`, `api/` and `intel/` are READ and IMPORT only. Build in `scripts/platformkit/tracking/`.
NEVER write `data/registry/`, never flip a flag, never touch `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.

**WHERE THIS ROW RUNS:** LOCAL (conda `basketball_ai`) for the router and the sheets; the sections come from
the staged corpora (`nba-track-a20/data/footage_corpus`, `nba-track-a6/data/footage_corpus`) and, for more
games, the pod corpus copied READ-ONLY to `/workspace/wt/<wt>/` scratch (never touch the daemon or guards).
Raters: two different codex model tiers (terra and sol) rating contact sheets BLIND (no router label
visible), as in G304's rater protocol; the orchestrator adjudicates disagreements by a third rater.

**WHY THIS ROW EXISTS.** G341's router reports 96.6-100 pct WIDE on sections whose contact sheets show
interstitials and close-ups; propagation and calibration are only meaningful on usable wide views. Astra:
validate the WIDE cue on held-out shots with a reject / UNKNOWN state, separate view classification from
geometric consistency, and use hard negatives (floor logos, static graphics, close-ups, wrong-template
courts). Without human labels, disclose model-rater agreement as a proxy and keep conservative UNKNOWN.

**PREMISE (step 0, BINDING before-condition):** run the landed G341 router on the 6 staged sections and
PRINT the view-class shares per section and one contact sheet per section (first frame of each shot, <= 200
KB). **If the router already emits UNKNOWN on >= 0.30 of frames on the close-up-heavy sections, the premise
(over-confident WIDE) is FALSE: STOP, write the memo, commit, report PREMISE FALSE.**

METHOD:
  1. **HELD-OUT SHOTS (sealed).** 60 shots from >= 6 games (sealed selection over the corpus by a rule that
     balances the router's predicted classes: 20 WIDE, 20 CLOSEUP, 20 CROWD/UNKNOWN by prediction), one
     representative frame + a 3-frame strip each; the rater sheets carry NO router label (blind).
  2. **RATING.** Two model raters (terra, sol) label each shot as USABLE_WIDE (floor visible with usable court
     structure) / CLOSEUP / CROWD_GRAPHICS / UNKNOWN with a one-line reason; disagreements go to a third
     rater; the adjudicated label is the reference; report inter-rater agreement (Cohen kappa) as the proxy
     for label quality.
  3. **SCORING.** Confusion counts router vs reference; precision of accepted WIDE and recall of USABLE_WIDE
     with Wilson 95 pct intervals; abstention share; per-game breakdown; 0 propagation across annotated
     cuts (check the G341 propagation output on the rated shots).
  4. **BAR (prereg it):** precision(WIDE) >= 0.95 and recall(USABLE_WIDE) >= 0.80 on the 60 shots; else the
     row reports the measured values and the router's WIDE cue is marked NOT VALIDATED for downstream use
     (G341 propagation and G334 calibration must then gate on UNKNOWN-safe rules).
  5. **TESTS.** The scorer on a hand-pinned 12-shot construct (known confusion, kappa); the sheet builder
     writes no router label into the sheet.
  6. CHANGE NOTHING ELSE.

**HONEST LIMITATIONS to state, not discover:** model raters are a proxy for human labels; 60 shots are a
screening; the reference cannot certify a negligible error rate; view class is not geometric validity.

ACCEPTANCE RULE:
  metric        = the sealed shot list; both raters' sheets + adjudication with kappa; the confusion table;
                  precision / recall with intervals; abstention share; the cut check; tests
  before        = the WIDE cue is unvalidated; contact sheets contradict 96.6-100 pct WIDE
  bar           = 60/60 shots rated by both raters (n), kappa reported; precision / recall with intervals
                  reported and the sealed bar applied (met or not); 0 router labels leaked into the sheets;
                  0 src edits
  n             = 60 shots from >= 6 games; 2 raters + adjudication
  eye check     = REQUIRED: the rated sheets are the evidence (<= 200 KB each, committed)
  must not move = `src/`, `data/`, `data/registry/`, the G341 router thresholds, every flag, the pod daemon
                  and guards, `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`
  verdict       = **VALIDATED** / **NOT VALIDATED** with the numbers; **PARTIAL** naming what could not run.
EVIDENCE: `docs/evidence/tracking/g350_wide_cue_validation_2026-09-08.md` (<= 60 lines; VERDICT line 1;
tables; NOT VERIFIED; wall time; SHA-256s) + `.../g350_wide_cue_validation_2026-09-08/shots.csv`,
`ratings.csv`, `confusion.csv`, `sheets/` (integer cells zero-padded; shares as ADDITIVE per-mille columns).
**ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT** (append only). **Do NOT edit
`docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.**
TEST: `tests/platformkit/test_g350_wide_cue_validation.py`, alone. **NEVER a full pytest.** Every new file
<= 300 lines.
DIVISION OF LABOUR: the codex lane prepares the prereg (sealed alone: the shot rule, the label set, the bar,
the rater protocol), the sheet builder, the scorer, the tests and the memo skeleton, and exits with the line
`agent: PREPARED FOR FINISHER` plus the exact commands; the orchestrator runs the blind raters and the
finisher scores (Q1). Absent sections or `data/registry` in the worktree are reported, never a stop.
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
