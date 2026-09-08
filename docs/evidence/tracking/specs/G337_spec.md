GAP G337 | sport basketball | worktree a13 | log cx_g337_nonplayer_box_gate

**PRODUCER ROW -- src/ EDITS AUTHORIZED (user, 2026-09-08 10:20 CDT).** Apply the landed PROPOSED
non-player box gate from G323 to the production route, behind a construct test and a before/after
measurement. NEVER write `data/registry/`, never flip a feature flag, never claim an edge, never touch
`docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md` or any threshold not named by the diff itself.

**WHERE THIS ROW RUNS:** LOCAL for code and tests; the pod is READ-ONLY (never touch `track_daemon` or the
guards 1039858 / 1519254; a daemon deploy may be in progress -- never write under `/workspace/nba-ai-system`).
Copy at most two <= 40 MB sections from the pod bridge/corpus for the smoke and delete them afterwards;
peak RSS under 1.5 GB; use the conda `basketball_ai` interpreter the route needs and print its version
line in the memo (this box has more than one interpreter).

**WHY THIS ROW EXISTS.** G323 measured non-player boxes (referees, bench, staff, courtside) in the person
stream and found no gate on the route; the fix was written as
`docs/research/organization-sprint/PROPOSED-g323-nonplayer-box-gate.md` (local-only; find the copy in
`C:/Users/neelj/nba-track-a6/docs/research/organization-sprint/` or any worktree; if no copy survives,
rebuild the gate from the G323 memo's stated rule and say so). Non-player boxes inflate rows per frame,
consume the 10 tracker slots (G310 found 134-559 instances per 40 frames on 10 slots) and poison
possession logic. G310 also found the route runs at conf 0.22 while the register cites 0.3 -- restate,
do not change.

**PREMISE (step 0, BINDING before-condition):** on one section, count boxes per emitted frame and the
share of boxes whose bottom-centre lies outside the court polygon (use the fallback homography the route
uses today; label it as such) or whose height is implausible for a player at that image position;
PRINT the table with n. **If fewer than 5 pct of boxes fail both plausibility checks, the premise is
FALSE for that section: try the second section; if both are under 5 pct, STOP, write the memo, commit,
report PREMISE FALSE.**

METHOD:
  1. Apply the PROPOSED gate as written (cite `file:line` before/after; a handful of lines in
     `src/tracking/player_detection.py` or wherever the diff targets; keep the touched file within its
     existing LOC allowlist). Additive: gated boxes are dropped from the PLAYER stream only; if the diff
     offers a `keep_nonplayer` flag or a separate `nonplayer` sidecar, default it to the diff's stated
     default; do not invent a new default.
  2. Construct test: a frame with 10 court boxes and 4 off-court/oversized boxes yields 10 player rows;
     an all-court frame is unchanged; an empty frame stays empty.
  3. BEFORE/AFTER on the two sections (fixed stride from a sealed offset, >= 40 frames each): boxes per
     frame, distinct instances (G310's instance key), share outside the court polygon, share with
     implausible height, ball rows unchanged (the gate must not touch the ball stream) -- all with n.
  4. CHANGE NOTHING ELSE.

**HONEST LIMITATIONS to state, not discover:** the court polygon comes from the fallback homography and
is itself wrong for most clips (G330), so "outside the court" is a proxy; the gate can drop real players
at the sideline -- report how many boxes with a plausible height were dropped for polygon reasons alone.

ACCEPTANCE RULE:
  metric        = the premise table; the diff with `file:line`; the construct test; the before/after
                  table with n; the plausible-height-dropped count
  before        = no non-player gate; premise share >= 5 pct on at least one section
  bar           = the construct test fails on old code and passes on new; ball rows byte-identical
                  before/after; the touched file does not exceed its allowlist; 0 register edits
  n             = 2 sections x >= 40 frames (screening); every box
  eye check     = OPTIONAL: 4 frames rendered with kept/dropped boxes (<= 200 KB each), illustrative only
  must not move = `data/`, `data/registry/`, every flag default, the pod, the daemon and guards, every
                  committed artifact, `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`
  verdict       = **DONE** if the bar holds; **PARTIAL** with the explicit list otherwise.
EVIDENCE: `docs/evidence/tracking/g337_nonplayer_box_gate_2026-09-08.md` (<= 60 lines; VERDICT line 1;
tables; NOT VERIFIED list; wall time; SHA-256s) + `docs/evidence/tracking/g337_nonplayer_box_gate_2026-09-08/
before_after.csv` (integer cells zero-padded to 6 digits). **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME
COMMIT** (one `>>` append, LF). **Do NOT edit `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.**
TEST: `tests/platformkit/test_g337_nonplayer_box_gate.py` plus the existing test file of every touched
module, each alone. **NEVER a full pytest.**
COMMIT: explicit pathspec only (src paths named). ASCII stdout. Prereg sealed as its OWN commit first
(embed the seal: last line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
