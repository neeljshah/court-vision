GAP G360 | sport basketball | worktree a3 | log cx_g360_court_presence_cue

**VIEW-CLASS ROW, SUCCESSOR TO G350 (WIDE cue NOT VALIDATED) AND G352 (all rule-selected sections were
press conferences / title cards). Codex PREPARES, a finisher MEASURES; the orchestrator runs blind model
raters as in G350.** `src/`, `kernel/`, `api/` and `intel/` are READ and IMPORT only. Build in
`scripts/platformkit/tracking/`. NEVER write `data/registry/`, never flip a flag, never edit the landed content
gate (`scripts/platformkit/footage_content_gate.py`) or the router thresholds, never touch
`docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.

**WHERE THIS ROW RUNS:** LOCAL (conda `basketball_ai`; `python -m` from the worktree root; per-clip reads) on
the staged corpora (`nba-track-a20/data/footage_corpus`, `nba-track-a6/data/footage_corpus`) plus READ-ONLY
pod fetches of sections named by the G350 candidates.csv (the corpus rotates: absent = ABSENT). Raters:
codex terra and sol on contact sheets that carry NO cue value (blind), adjudication by the orchestrator's
delegate from the sheet, as in G350 (kappa 0.8429 there).

**WHY THIS ROW EXISTS.** Three landed rows show that nothing in the program can tell a court from a
non-court section: G350 measured the G341 WIDE cue at precision 0.10 on 22 blind-rated shots (18 of 20
router-WIDE shots were commercials, bumpers, close-ups, black frames, ceremonies); G352's sealed rule
picked 4 sections that were all press conferences or title cards; and the landed HSV content gate
returns "review" on the press conferences (surface 54 to 58 per mille), "accept" on the title-card section
(a floor close-up counts as tan surface) and "reject" only on static frames. Every registration or ball
row downstream needs a court-presence gate that is VALIDATED against a blind reference.

**PREMISE (step 0, BINDING before-condition):** on the 22 G350-rated sheets (adjudicated labels landed in
`g350_wide_cue_validation_2026-09-08/ratings.csv`), compute two cheap cues per representative frame: (a)
the landed content gate's max surface fraction; (b) a LINE-FAMILY cue = the number of long straight
segments (LSD or Hough, >= 8 pct of the frame width) grouped by orientation into >= 2 families with a
consistent vanishing direction. PRINT both cues against the reference label. **If NEITHER cue separates
USABLE_WIDE from the rest with AUC >= 0.75 on those 22, the premise is FALSE: STOP, write the memo, commit,
report PREMISE FALSE (a learned cue is then the next row, not this one).**

METHOD:
  1. **CUE (`court_presence_cue.py`, <= 200 lines):** `court_presence(frame) -> (score, families, longest_px,
     surface)`; deterministic; the sealed rule combines the line-family count and the surface fraction
     with thresholds PREREGISTERED from the premise (no tuning on the held-out set).
  2. **HELD-OUT SET (sealed BEFORE rating):** >= 200 representative frames sampled EVENLY (never a head
     slice) across >= 20 sections from >= 10 games and >= 3 competitions, drawn from the G350
     candidates.csv population plus post-epoch clips, each by full path + sha256 + frame index; balanced
     by the CUE'S prediction (>= 60 predicted court, >= 60 predicted non-court, the rest by the cue's
     abstention band) so that both error types are measurable; blind sheets (frame + 3-frame strip, no
     cue value) <= 200 KB each.
  3. **RATING:** two model raters (terra, sol) label USABLE_COURT / CLOSEUP / CROWD_GRAPHICS / UNKNOWN with a
     one-line reason; disagreements adjudicated blind by the delegate; Cohen kappa reported.
  4. **SCORING:** confusion cue vs reference; precision of predicted court and recall of USABLE_COURT with
     Wilson 95 pct intervals; abstention share; per-competition breakdown. **Bar (prereg it):** precision
     >= 0.90 and recall >= 0.80 on >= 200 rated frames (n >= 30 per predicted class); else NOT VALIDATED with
     the numbers.
  5. **CONSUMER (only if VALIDATED):** a PROPOSED feeder gate line (docs/research, gitignored, sha256 in the
     memo) and the G352 section rule amendment text; no src hook; no flag.
  6. CHANGE NOTHING ELSE.

**HONEST LIMITATIONS to state, not discover:** model raters are a proxy for human labels; a court-presence
cue says nothing about geometric validity (G330); 200 frames are a screening; the premise reuses 22
already-rated sheets (never part of the held-out set).

ACCEPTANCE RULE:
  metric        = the premise AUC table; the sealed held-out list; both raters' sheets + adjudication with
                  kappa; the confusion table; precision / recall with intervals; abstention; per-competition
  before        = no validated court-presence cue (WIDE 0.10; content gate review / accept on non-court)
  bar           = held-out sealed before rating and evenly sampled; >= 200 frames / >= 20 sections / >= 10
                  games / >= 3 competitions; 0 cue values leaked into sheets; kappa reported; the sealed
                  bar applied (met or not); 0 src edits; 0 threshold tuning after the seal
  n             = >= 200 frames; 2 raters + adjudication
  eye check     = REQUIRED: the rated sheets are the evidence (<= 200 KB each, committed)
  must not move = `src/`, `data/`, `data/registry/`, the landed content gate, the router thresholds, every
                  flag, the pod daemon and guards, `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`
  verdict       = **VALIDATED** / **NOT VALIDATED** with the numbers; **PARTIAL** naming what could not run;
                  **PREMISE FALSE** with the AUC table.
EVIDENCE: `docs/evidence/tracking/g360_court_presence_cue_2026-09-08.md` (<= 60 lines; VERDICT line 1; tables;
NOT VERIFIED; wall time; SHA-256s) + `.../g360_court_presence_cue_2026-09-08/premise.csv`, `heldout.csv`,
`ratings.csv`, `confusion.csv`, `sheets/`, `raters/` (integer cells zero-padded; shares as ADDITIVE per-mille
columns). **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT** (append only). **Do NOT edit
`docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.**
TEST: `tests/platformkit/test_g360_court_presence_cue.py` (synthetic court with two line families scores
above a synthetic crowd frame; the sheet builder writes no cue value), alone. **NEVER a full pytest.** Every
new file <= 300 lines.
DIVISION OF LABOUR: the codex lane prepares the prereg (sealed alone: the cue definition, the premise AUC
rule, the even-sampling rule, the balance rule, the label set, the bar), the cue module, the sheet builder,
the scorer, the test and the memo skeleton, and exits with the line `agent: PREPARED FOR FINISHER` plus the
exact commands in `python -m` form; the finisher runs the premise, seals the held-out set, runs the blind
raters and scores (Q1). Absent sections or `data/registry` in the worktree are reported, never a stop.
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
