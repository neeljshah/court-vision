GAP G379 | sport basketball | worktree a14 | log cx_g379_broadcast_geometry

**BROADCAST GEOMETRY ROW (astra next-rows seed BROADCAST_GEOMETRY; the registration wall). Landed inputs: G362 (registration
refusal; known-H 1.6516 px; broadcast stages NEVER RUN -- the known-H <= 1.0 px prerequisite stopped them), G365 (CLOSED AT LIMIT:
candidate B refinement 1.1287 / 1.1165 / 0.7636 px on G1 / G3 / G4 and 469.3808 on G2_WIDE; the G2 carve-out REJECTED), G371 (DONE:
truth-free selector refuses -- one symmetry class, NO_DISTINCT_RUNNER_UP 357/360, 0 ACCEPT), G370 (every section IMAGE_ONLY),
G374 (PARTIAL: the frozen court-presence head validates at precision 0.962 / recall 0.967 on 300 blind frames; abstention 47 per
mille). This row measures REAL broadcast registration under those frozen pieces; it does not refit any of them.** Codex PREPARES, a
Claude finisher MEASURES on the pod; blind references on the PC. `src/`, `kernel/`, `api/`, `intel/`,
`domains/basketball/tracking/line_calibration.py` READ and IMPORT only. Build additively in `scripts/platformkit/tracking/g379_*.py`
(import g362_fit_validate / g365_refine_b / g371_symmetry_margin / g364_predict; copy none). NEVER write `data/registry/`, never
flip a flag, never move a G362 / G365 / G371 / G374 bar or threshold (0.30 stays), never refit the head, never touch the register.

**WHERE THIS ROW RUNS:** ON THE POD, `/workspace/wt/aXX`; sources = fresh sections pinned per G361 and copied to scratch BEFORE the
quota guard prunes them (files >= 90 min old above 35 GB; scratch < 2 GB); CPU for fitting, GPU only for the frozen presence head
(one job at a time); references = codex terra + sol on the PC under the RAM gate.

**PREMISE (step 0, BINDING before-condition):** re-read G362's known_h.json / premise, G365's summary_b.json, G371's summary.json and
G374's summary.json and PRINT the numbers above; **if any landed row already reports a broadcast (non-synthetic) registration with
forward median <= 8 px at 720p on >= 4 sections, the premise is FALSE: STOP, memo, commit, report.**

METHOD (sealed before any fit or rating):
  1. **SCREEN (fixed, sealed BEFORE any fit):** six sections from >= 4 games drawn EVENLY from the sections the G374 head marks COURT
     on >= 0.50 of 12 interior ticks (presence probability >= 0.30, its frozen threshold); 60 unique decoded frames per section at
     even spacing; the split of line strokes into FIT and VALIDATION is fixed per frame by a seeded rule BEFORE fitting.
  2. **FIT:** the landed G362 fitter + G365 candidate-B refinement on FIT strokes only; selection by the G371 truth-free rule
     (FIT objective J; a refusal is a refusal -- NO_DISTINCT_RUNNER_UP stays NO_DISTINCT_RUNNER_UP; no override, no oracle).
  3. **VALIDATE the selected matrix (never a refit):** G362's held-out validation on the reserved strokes exactly as landed:
     bidirectional residual <= 8.0 px at 720p, PENALTY_PX 64.0 over all template points, >= 2 line families, >= 30 unique
     fixed-density supports at spacing 6.0; statuses VALID / NO_LINES / NO_VALIDATION / REFUSED kept distinct and all in N.
  4. **FEET:** independently detected feet (the deployed route) mapped through the selected H; feet_inside share; forward residual
     median per section pooled over points.
  5. **NEGATIVES:** >= 200 unique blind non-court frames from >= 30 sections (G374-style presence labels by terra + sol, adjudicated):
     the presence cascade must accept ZERO of them; NO_LINES / NO_VALIDATION on negatives stay counted, never as passes.
  6. **ORIENTATION:** masked UNKNOWN unless G378 lands a supported cue; reported separately; no absolute-orientation claim from lines.
  7. CHANGE NOTHING ELSE; no flag; no src hook; G362's historical failures preserved beside.

ACCEPTANCE RULE:
  metric        = per section: VALID share of scheduled decoded frames; feet_inside share; forward residual median (720p); raw fitter
                  vs presence-cascade outcomes SEPARATELY; refusal statuses per frame; negatives accepted / 200
  before        = G352 0/4 measured (six required); G362 broadcast stages never run; G371 0 accepts on synthetic
  bar           = six sections / >= 4 games, 60 unique decoded frames and >= 100 feet EACH; >= 4/6 sections with VALID >= 0.50 AND
                  feet_inside >= 0.60 AND forward median <= 8 px; cascade accepts 0/200 negatives; every G362 validity constant
                  unchanged; 0 refits; the six-section conclusion is descriptive (PARTIAL for any sampled section-level claim)
  n             = 6 sections (screen), 360 frames, >= 100 feet each; negatives >= 200 frames / >= 30 sections; >= 30 frames per
                  scored stratum, else descriptive
  eye check     = REQUIRED: 30 evenly spaced source-bound renders across ALL statuses (VALID, NO_LINES, NO_VALIDATION, REFUSED)
  must not move = G362 / G365 / G371 / G374 code, constants, statuses and thresholds; the deployed route; every flag; `data/registry/`
  verdict       = **DONE** (every clause) / **PARTIAL** (name the clause; masks named) / **PREMISE FALSE**
EVIDENCE: `docs/evidence/tracking/g379_broadcast_geometry_2026-09-10.md` (<= 60 lines; VERDICT line 1; NOT VERIFIED; wall time; GPU
minutes; SHA-256s) + `.../g379_broadcast_geometry_2026-09-10/{prereg,screen.csv,source_identity.csv,stroke_split.csv,selected_H.json,
residuals.csv,feet.csv,negatives.csv,refusals.csv,presence_margin_audit.csv,summary.json,renders/}`. **ADD ONE RESULTS_LEDGER.md ROW.**
TEST: `tests/platformkit/test_g379_broadcast_geometry.py` alone (stroke split fixed before fit; validation never refits; negatives never
pass; the seal). **NEVER a full pytest.** Every new file <= 300 lines. Vocabulary follows contract Q6; automated scan required. Prereg
sealed as its OWN commit first. ASCII stdout. **NEVER PARK.**

VERSION 2026-09-10
