GAP G315 | sport all | worktree aXX | log g315_same_id_step_screen
**MEASUREMENT ONLY -- A SCREEN, NOT A FIX. `src/`, `domains/`, `api/`, `kernel/` and `intel/` are
READ and IMPORT only. Build in `scripts/platformkit/`. This row proposes NO production change,
moves no threshold and adopts nothing.**

**WHERE THIS ROW RUNS:** LOCAL for the arithmetic; the contact sheets need the pod
`tracking_data.csv` files AND the source frames. **Renders are HEADLESS ONLY (`--no-show`), never
`cv2.imshow`.** Pod reads are READ-ONLY into a scratchpad -- **never into `data/` in the repo.**
**NEVER stop, signal or interfere with `track_daemon`.**

**WHY THIS ROW EXISTS.** G309 measured the 95th percentile per-track consecutive-observation
displacement of the bbox bottom-centre, normalised by `source_height`, at **median 0.73 of frame
height (min 0.4348 @ ncaa_sRtHQbywiTE, max 0.8594 @ wnba_05, n = 13)**. **A 95th-percentile stride
of most of the frame between two consecutive observations carrying the SAME id is an association
signal, not a motion one** -- no player crosses three quarters of a broadcast frame in one sampled
step. If that reading holds, `median_track_len_rows` is measuring the length of a stitched-together
identity rather than the length of a track, and the id-churn figures are correspondingly optimistic.

**PREMISE (step 0, BINDING before-condition):** on **3** censused games, recompute the per-track
step distribution from the fetched `tracking_data.csv` under the G309 conventions (footpoint =
`((bbox_x1+bbox_x2)/2, bbox_y2)`; a step is two consecutive same-`player_id` observations ordered
by frame with NO interpolation across a gap; displacement is Euclidean image px divided by
`source_height`; p95 is nearest-rank) and **PRINT, per game: `n_steps`, the median, p75, p95 and
max normalised step, and the share of steps above 0.3.** **If p95 is below 0.3 on any of the three,
the premise is FALSE: STOP, write the memo, commit, and report PREMISE FALSE.**

METHOD:
  1. **SCREEN, DO NOT FIX.** Per game, count the id-swap CANDIDATES: steps above **0.3** of frame
     height within a single `player_id`. Report the count, its share of `n_steps`, and the
     distribution of the frame GAP each candidate spans -- **a large step across a large gap is not
     the same claim as a large step across one stride, and the two must be reported separately.**
  2. **CONTACT SHEETS: 10 examples per game**, headless renders, each panel showing the two frames
     of one candidate step with both boxes drawn and the id, frame indices and normalised step
     printed on it. **Examples are drawn EVENLY across the candidate distribution, not the top 10**
     -- a top-10 sheet only ever shows the tail. Name the sampling rule in the memo.
  3. **TWO MODEL RATERS**, independently, label each of the 30 examples SWAP / NOT-SWAP /
     UNREADABLE against a written rubric fixed BEFORE any panel is seen. **Report per-rater counts,
     the agreement rate and every disagreement**; do NOT adjudicate disagreements into a single
     number and do NOT report a consensus rate as if it were ground truth.
  4. **CHANGE NOTHING.** No production edit, no threshold, no proposal, no adoption.

**HONEST LIMITATIONS to state, not discover:** **two model raters are NOT ground truth.** They are
two correlated readers of the same rendered panels, they share the failure modes of the model that
runs them, and 30 examples over 3 games is a screen for whether a labelling effort is worth
mounting -- **it establishes no swap RATE for any game and none of these numbers may be quoted as
one.** Image space only: no court, foot, metre or registration claim. All 13 games are
`passed = false`. A large same-id step has innocent causes this row cannot exclude -- a camera cut,
a pan, a re-detection after occlusion -- and the gap-conditioned reporting of step 1 is the only
control offered against them.

ACCEPTANCE RULE:
  metric        = the per-game step distributions; the candidate count and share per game; the
                  gap-conditioned split; 30 labelled examples with per-rater counts and agreement
  before        = median p95 normalised same-id step 0.73 (n = 13) with NO example ever looked at
                  and no swap screen anywhere in the programme
  bar           = **NO pass bar. This row is descriptive.** Its success is the three reproduced
                  distributions, 30 rendered examples and two independent rater columns; **finding
                  that most candidates are innocent is a FULL SUCCESS and must be reported as one.**
  n             = 3 games; `n_steps` per game named; 30 examples (10 per game); 2 raters
  eye check     = the 30 contact-sheet panels, evenly sampled, both raters, disagreements listed
  must not move = `data/tracking/` on the pod (READ ONLY); the running `track_daemon`; `src/`,
                  `domains/`, `api/`, `kernel/`, `intel/`; `tracking_harness.py`; every threshold
EVIDENCE: `docs/evidence/tracking/g315_same_id_step_screen_2026-09-07.md` (<= 60 lines) with the
distributions, the candidate counts, the rater table and a **NOT VERIFIED** list; the contact
sheets committed beside it. **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT** (one `>>` append).
**Do NOT edit `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`** -- the orchestrator owns it.
TEST: `tests/platformkit/test_g315_same_id_step_screen.py` -- a SYNTHETIC construct pinning the
step, gap and candidate arithmetic against hand-computed values. **n = 1 (CONSTRUCT).** Run that
ONE file. **NEVER a full pytest.**
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first. **NEVER PARK.**
