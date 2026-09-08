GAP G352 | sport basketball | worktree aX | log cx_g352_calibration_whole_template_objective

**REGISTRATION ROW, SUCCESSOR TO G334 (preregistered objective change; codex PREPARES, an Opus finisher
MEASURES on the pod).** `src/`, `kernel/`, `api/` and `intel/` are READ and IMPORT only. Build in
`scripts/platformkit/tracking/` on top of the landed G334 modules (`g334_court_line_calibration.py`,
`g334_court_template.py`, `g334_merge.py`, `g334_metrics.py`, `g334_run.py`; reuse, never fork). NEVER write
`data/registry/`, never flip a flag, never touch `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`. No src
hook in this row (a hook needs the bar to hold first).

**WHERE THIS ROW RUNS:** the codex lane prepares locally on synthetic courts; the finisher runs on the pod as
CPU scratch under `/workspace/wt/<wt>/` (nice -n 19; OMP_NUM_THREADS=2; nohup detached; never touch the
daemon or the guards; never write under `/workspace/nba-ai-system`, never `/tmp`).

**WHY THIS ROW EXISTS.** G334 (2026-09-08, MEASURED -- BAR NOT MET, 0/6 sections for both arms) named three
defects that this row fixes by preregistration, not by tuning: (1) the sealed score was the mean over the
SURVIVING template points, so the argmax projects most of the 398-point template out of frame and lands
the rest on any bright straight structure (advertising boards); (2) the forward-px metric was buyable by
densifying the held-out set (the route "cleared" 8 px on S1 while placing 0 of 408 feet on the court);
(3) 3 of 6 sealed sections contained no court (a QR card, two press conferences) because the selection rule
filtered on filename and height only. Astra's self-training plan needs a direct teacher whose seed gate is
honest before any student is trained; this row is that gate.

**PREMISE (step 0, BINDING before-condition):** on the landed G334 S1 render, recompute the sealed objective
for the argmax fit and for the identity-free "all points in frame" alternative with the WHOLE-template
denominator: show the argmax loses under the whole-template score (n points in frame / 398 per fit).
**If the argmax also wins under the whole-template score, the premise is FALSE: STOP, write the memo,
commit, report PREMISE FALSE.**

METHOD:
  1. **OBJECTIVE (prereg it, before any real frame is scored).** Score = mean symmetric distance over the
     WHOLE template (an out-of-frame or unsupported template point contributes the sealed penalty
     distance, never nothing) with the validity gate INSIDE the search (a hypothesis with fewer than the
     sealed minimum in-frame template points, an implausible scale, a folded or reflected mapping, or fewer
     than 2 orientation families is rejected before scoring, not only at the argmax); reserve >= 25 pct of
     physical supports (whole markings, never split lines) as held-out BEFORE hypothesis search; the same
     held-out set for every arm (astra section 1 gate).
  2. **SECTION SELECTION (sealed).** Candidates = sections with a G346 LIVE verdict and a G341 WIDE share
     >= 0.5 (or, if G350 has not validated the cue, an eye-checked "court visible in the centre frame"
     contact sheet committed BEFORE scoring, <= 200 KB each); >= 6 sections across >= 4 games; the rule
     names each section by full path + sha256 in the prereg; the court template per section chosen by G342's
     selector when its decision is not UNKNOWN, else NBA for NBA/WNBA feeds and FIBA for eurocup/euroleague/
     nbl feeds (labelled ASSUMED).
  3. **ARMS.** ARM_A = G334's fitter with the new objective; ARM_B = ARM_A + the sealed LSD threshold from
     G334 arm B; ROUTE = the production homography on the SAME held-out set (never a densified one).
  4. **METRICS per section, per arm (n everywhere):** validH share; feet inside the 94x50 (or 28x15 m) court /
     detected feet (n >= 100 per section or say why not); held-out forward px (median, p90) on the common
     held-out set; whole-template in-frame share; bootstrap (32 x 1 px) foot spread p95 in ft; runner-up
     margin. Bar (sealed, unchanged from G334): feet inside >= 0.60 at n >= 100, validH >= 0.50, forward
     median <= 8 px, on >= 4 of 6 sections.
  5. **FAILURE BUCKETS** counted per frame (too_few_groups, no_valid_h, implausible_scale, folded, low_margin)
     with the render of one frame per bucket per section (<= 200 KB).
  6. CHANGE NOTHING ELSE. No src hook.

**HONEST LIMITATIONS to state, not discover:** zoom-ins and replays cannot be labelled automatically (G242);
the court template is assumed where G342 abstains; a synthetic-court pass is not a broadcast pass; six
sections are a screening; the objective change is preregistered here, never derived from the scored frames.

ACCEPTANCE RULE:
  metric        = premise recomputation; the sealed section list with digests; per section x arm metrics
                  with n; failure buckets; renders
  before        = G334 0/6 with the surviving-points objective; route feet inside 2/950
  bar           = the sealed bar above on >= 4 of 6 sections (met or not); every arm scored on the SAME
                  held-out set (assert digests); every cell carries n; 0 src edits; 0 objective changes after
                  the seal
  n             = >= 6 sections x >= 60 evaluated frames x 3 arms; every detected foot
  eye check     = REQUIRED: one render per section per arm + the pre-scoring contact sheets (<= 200 KB each)
  must not move = `src/`, `data/`, `data/registry/`, every flag, the pod daemon and guards, G334's landed
                  artifacts, `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`
  verdict       = **MEASURED -- BAR MET** or **MEASURED -- BAR NOT MET** with the per-section table;
                  **PARTIAL** naming the arm or section that could not run.
EVIDENCE: `docs/evidence/tracking/g352_calibration_whole_template_2026-09-08.md` (<= 60 lines; VERDICT line 1;
tables; NOT VERIFIED; wall time; SHA-256s) + `.../g352_calibration_whole_template_2026-09-08/metrics.csv`,
`buckets.csv`, `renders/` (integer cells zero-padded; shares as ADDITIVE per-mille columns). **ADD ONE
RESULTS_LEDGER.md ROW IN THE SAME COMMIT** (append only). **Do NOT edit
`docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.**
TEST: `tests/platformkit/test_g352_whole_template_objective.py` (synthetic court: the whole-template score
ranks the true H above an out-of-frame fold; the in-search validity gate rejects a reflected mapping; exact
lines reproduce truth to < 1e-6 px) plus `tests/platformkit/test_g334_court_line_registration.py`, each
alone. **NEVER a full pytest.** Every new file <= 300 lines.
DIVISION OF LABOUR: the codex lane prepares the prereg (sealed alone: the objective, the penalty distance,
the in-search gates, the section rule, the held-out reservation rule), the objective module, the tests and
the memo skeleton, and exits with the line `agent: PREPARED FOR FINISHER` plus the exact pod commands; the
finisher (Opus) seals the section list with contact sheets, runs the arms on pod scratch and writes the
memo (Q1). Absent sections or `data/registry` in the worktree are reported, never a stop.
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
