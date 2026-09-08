GAP G355 | sport basketball | worktree aX | log cx_g355_shot_router_robustness

**ROBUSTNESS ROW ON LANDED CODE (from the G350 finisher 2026-09-08; codex-friendly, local, synthetic + golden
rerun).** `src/`, `kernel/`, `api/` and `intel/` are READ and IMPORT only. Edit ONLY
`scripts/platformkit/tracking/shot_router.py` and `scripts/platformkit/tracking/floor_motion.py` (landed
G341 adbc9ba94) plus their tests. NEVER write `data/registry/`, never flip a flag, never move a G341
threshold, never touch `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.

**WHY THIS ROW EXISTS.** The G350 finisher reproduced two defects in the landed G341 code: (1) `shot_router.py`
(around line 68) raises `ValueError` on any frame pair where the second frame yields exactly ONE ORB
descriptor (a 1-D descriptor array reaches the matcher), which aborted a full-corpus router pass in under
a minute; (2) `floor_motion.propagate_frames` emits NO row for a shot's FIRST frame, so a 1-frame shot has
zero propagation records and downstream cut checks raise. Both are crash / omission defects, not threshold
questions; the fix must leave every landed G341 output byte-identical on the six landed sections.

**PREMISE (step 0, BINDING before-condition):** reproduce both defects with minimal constructs: (1) a frame
pair whose second frame produces one descriptor -> `ValueError` traceback (cite the line); (2) a synthetic
shot of one frame -> 0 propagation rows. **If either does not reproduce on master's landed code, report it
as NOT REPRODUCED and fix only the one that does; if neither reproduces, the premise is FALSE: STOP, write
the memo, commit, report PREMISE FALSE.**

METHOD:
  1. **FIXES (additive, minimal).** (1) Guard the descriptor shape: zero or one descriptor on either frame
     => the pair is UNOBSERVABLE with reason `too_few_descriptors` (an existing reason code if one fits;
     never a silent skip; the frame stays in the denominator per G341 B1). (2) `propagate_frames` emits a
     row for the first frame of every shot with state `ANCHOR` (or the existing anchor state) and the same
     columns; existing columns unchanged (B2).
  2. **TESTS (failing-then-passing).** Add the two constructs to `tests/platformkit/test_g341_shot_router.py`
     (or a new `test_g355_shot_router_robustness.py`, <= 120 lines): each test FAILS on the landed code (show
     the failing run in the memo) and passes after the fix.
  3. **GOLDEN RERUN.** Re-run the router + propagation on the six landed G341 sections (local staged
     corpora `nba-track-a20/data/footage_corpus`, `nba-track-a6/data/footage_corpus`; the sections are named
     with sha256 in the landed G341 memo) and compare `shots.csv` and `propagation.csv` to the landed
     `docs/evidence/tracking/g341_shot_router_2026-09-08/` byte-for-byte EXCEPT the additive first-frame
     anchor rows (report their n); any other difference is a regression: report and STOP.
  4. CHANGE NOTHING ELSE.

**HONEST LIMITATIONS to state, not discover:** a robustness fix does not validate the WIDE cue (G350);
the golden rerun covers six sections only; a section absent locally is reported ABSENT (the golden check
then covers the remaining sections and the verdict is PARTIAL).

ACCEPTANCE RULE:
  metric        = premise reproductions (tracebacks / counts); the two tests failing-then-passing; the
                  golden byte-identity table (6 sections x 2 files, differences n, anchor rows n)
  before        = router crashes on a single-descriptor frame; first frame of a shot has no propagation row
  bar           = both defects reproduced and fixed; 2/2 new tests pass and the landed 8 G341 tests pass
                  unchanged; golden identity on every available section except the additive anchor rows;
                  0 threshold moves; every file <= 300 lines; 0 src edits
  n             = 2 constructs; 6 sections
  eye check     = NONE. Say that.
  must not move = every G341 threshold, `src/`, `data/`, `data/registry/`, every flag, the landed G341
                  artifacts, `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`
  verdict       = **DONE** if the bar holds; **PARTIAL** naming what could not run.
EVIDENCE: `docs/evidence/tracking/g355_shot_router_robustness_2026-09-08.md` (<= 60 lines; VERDICT line 1;
tables; NOT VERIFIED; wall time; SHA-256s) + `.../g355_shot_router_robustness_2026-09-08/golden.csv` (integer
cells zero-padded). **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT** (append only). **Do NOT edit
`docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.**
TEST: `tests/platformkit/test_g341_shot_router.py` and the new test file, each alone. **NEVER a full pytest.**
DIVISION OF LABOUR: the codex lane prepares the prereg (sealed alone: the two constructs, the reason code,
the anchor-row rule, the golden rule), the fixes, the tests and the memo skeleton with the failing-run
evidence, and exits with the line `agent: PREPARED FOR FINISHER` plus the exact golden-rerun commands; the
finisher runs the golden rerun (Q1). Absent sections are reported, never a stop.
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
