GAP G349 | sport basketball | worktree aX | log cx_g349_ball_ownership_survival

**DIAGNOSIS ROW (astra midday review 2026-09-08, item D; follows G344 PARTIAL). Codex PREPARES, a finisher
MEASURES.** `src/`, `kernel/`, `api/` and `intel/` are READ and IMPORT only. Build in
`scripts/platformkit/tracking/`. NEVER write `data/registry/`, never flip a flag, never loosen the sealed
ownership radius to manufacture coverage, never touch `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.

**WHERE THIS ROW RUNS:** LOCAL only (conda `basketball_ai`; batch reads per window; check free RAM first).
Inputs: the landed G339 join harness (`ball_join.py`) and the landed G344 state machine
(`ball_shadow_possession.py`, `g344_synthetic.py`), the local tracking mirror `data/tracking/<game_id>/`
and the 2 WNBA tables; the G346 frozen list (exclude frozen sources); the G341 shot tables where present.

**WHY THIS ROW EXISTS.** G344 passed 200/200 synthetic cases but on 24 real windows + 2 WNBA tables an
ownership hypothesis survived on 1 of 1,560 frames and the +/- 1 s shuffle control did not move. Before
any consumer is fed, the program must know WHERE the ball evidence dies: the frame join, the source age,
coordinate compatibility (ball px vs player px at the same resolution), the radius, the motion-agreement
test, or the abstention rules. Only proven join / unit / timing defects may be corrected, then an
untouched evaluation sample is resealed before ownership is assessed again.

**PREMISE (step 0, BINDING before-condition):** on the 24 G344 windows print the survival counts of the
G344 run per stage (frames F; frames with any ball row; detected ball; player rows in frame; player within
radius; motion pairs available (3-frame history on both); motion agreement; accepted ownership). **If the
first stage where survival drops below 0.10 of F is `frames with any ball row` (the join itself), the
premise is a JOIN defect: fix it in this row and reseal; otherwise continue.**

METHOD:
  1. **SURVIVAL TABLE (`g349_ball_survival.py`, <= 250 lines).** Stage-by-stage counts and shares (per window
     and pooled) with the reason at each drop; coordinate compatibility check: ball px range vs player px
     range and `source_height` per table (a mismatch = unit defect, named); age distribution of detected
     ball rows; the share of frames where the 3-frame history prerequisite is missing (the G344 verifier's
     NEW GAP: add a `prerequisite_available` field).
  2. **DEFECT CORRECTIONS.** Only proven join / unit / timing defects are corrected (each with a test that
     fails on the old code); record every correction. No threshold moves.
  3. **RESEALED EVALUATION.** Seal >= 30 live windows from >= 3 games including 2 basketball competitions
     (NBA + WNBA), requiring >= 100 eligible observed-ball motion pairs overall; rerun the G344 state machine
     unchanged (thresholds sealed) and the +/- 1 s shuffle control; report the full-frame AND eligible-pair
     denominators together; ablate observed vs inferred ball rows.
  4. **CONSUMER-BLINDNESS CONTROL.** Swap ball trajectories between two same-view windows and remove the ball
     input entirely; if any downstream reader on master (G339 census) would see unchanged features, say the
     consumer is blind (expected today).
  5. CHANGE NOTHING ELSE. No consumer wiring.

**HONEST LIMITATIONS to state, not discover:** coverage and shuffle response establish sensitivity, not
ownership correctness; nearest player is not the handler; if support stays sparse the honest deliverable is
missingness / age indicators and abstention, not a possession label.

ACCEPTANCE RULE:
  metric        = the survival table with n per stage; the named defect(s) with tests; the resealed
                  evaluation (ownership share of F, eligible pairs n, motion agreement, shuffle delta);
                  the consumer-blindness control
  before        = G344: owner 1/1,560; shuffle control flat; cause unlocated
  bar           = every stage has n; every correction is proven by a failing-then-passing test; the
                  resealed evaluation reports both denominators; the shuffle bar (>= 20 pp) is applied as
                  sealed (met or not); 0 threshold moves; 0 src edits
  n             = 24 windows (diagnosis) then >= 30 windows / >= 3 games / >= 100 motion pairs
  eye check     = NONE. Say that.
  must not move = `src/`, `data/`, `data/registry/`, every G344 threshold, every flag, every landed
                  artifact, `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`
  verdict       = **DONE** with the located cause (and the resealed result) if the bar holds; **PARTIAL**
                  naming what could not run.
EVIDENCE: `docs/evidence/tracking/g349_ball_ownership_survival_2026-09-08.md` (<= 60 lines; VERDICT line 1;
tables; NOT VERIFIED; wall time; SHA-256s) + `.../g349_ball_ownership_survival_2026-09-08/survival.csv`,
`resealed_states.csv` (integer cells zero-padded; shares as ADDITIVE per-mille columns; never rename or
remove a column). **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT** (append only). **Do NOT edit
`docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.**
TEST: `tests/platformkit/test_g349_ball_survival.py` plus `tests/platformkit/test_g344_ball_shadow_possession.py`,
each alone. **NEVER a full pytest.** Every new file <= 300 lines.
DIVISION OF LABOUR: the codex lane prepares the prereg (sealed alone: stages, the resealing rule, the
denominators), the module, the tests and the memo skeleton, and exits with the line `agent: PREPARED FOR
FINISHER` plus the exact commands; it must NOT run the real windows itself (Q1). A missing local mirror or
`data/registry` in the worktree is reported, never a stop.
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
