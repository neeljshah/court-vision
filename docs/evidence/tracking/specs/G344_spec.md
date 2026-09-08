GAP G344 | sport basketball | worktree aX | log cx_g344_ball_shadow_possession

**BALL EVIDENCE -> SHADOW POSSESSION STATE (label-free; local; codex PREPARES, a finisher MEASURES).**
`src/`, `kernel/`, `api/` and `intel/` are READ and IMPORT only. Build in `scripts/platformkit/tracking/`.
NEVER write `data/registry/`, never flip a flag, never claim an edge, never feed the simulator in this row,
never touch `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`. No video, no GPU, no pod.

**WHERE THIS ROW RUNS:** LOCAL only (conda `basketball_ai`; print the interpreter line). Inputs: the G339
join harness `scripts/platformkit/tracking/ball_join.py` (landed on master; reuse, never duplicate), the two
committed WNBA tables under the G314/G320 artifacts, and the local tracking mirror
`data/tracking/<game_id>/` for the 24 sealed G343 windows (the same window list; if G343 has not landed,
seal the same rule here and say so).

**WHY THIS ROW EXISTS.** G335 measured the ball IS detected on a median 0.8667 of frames, and G339 measured
that the possession simulator and the feature layer never read `ball_tracking.csv` (BALL_BLIND). The ball
therefore has zero downstream effect. Astra's ranked row 5 (2026-09-08): join the observed ball evidence
into a SHADOW possession state with explicit source / age / confidence fields and abstention, prove the
join on synthetic cases, and measure how much of the frame denominator carries a usable ownership
hypothesis -- as a proxy-supported state, never as true possession.

**PREMISE (step 0, BINDING before-condition):** run `ball_join.py --report` on the two committed WNBA tables
and PRINT frames-with-ball / frames-without / nearest-player distance quantiles (n). **If a joined per-frame
ownership state with source, age and confidence fields already exists on master (grep `ownership`,
`possession_state`, `ball_owner` under `scripts/platformkit/` and `src/`), the premise is FALSE: STOP,
write the memo, commit, report PREMISE FALSE.**

METHOD:
  1. **STATE (`scripts/platformkit/tracking/ball_shadow_possession.py`, <= 250 lines).** Per frame over the
     denominator F = every frame index in the window (decode failures and missing rows included as
     ABSENT): state in {OBSERVED_VALID, INFERRED, ABSENT, AMBIGUOUS}; `source` (detected / inferred /
     none), `age_frames` since the last detected ball, `confidence` (the detector's, else null). Ownership
     hypothesis: the nearest player box (image px, bottom-centre) within a sealed radius (60 px at 720p,
     scaled by height) AND motion agreement over the last 3 frames (cosine between ball and player
     displacement >= 0.5, magnitude ratio in [0.5, 2.0]); otherwise ABSTAIN with the reason (no ball, no
     player in radius, two players within 10 px of each other, motion disagreement). Never assign
     ownership across a G341 cut if a shot table exists (else state that cuts are unknown). Airborne ball
     pixels are image coordinates, not floor positions: say so in the docstring and the memo.
  2. **SYNTHETIC CASES (200, sealed seed).** Constructed player + ball tables with known truth: offset
     ball timestamps, a cut mid-window, missing ball rows, duplicate ball rows, a player passing through
     the ball radius without motion agreement. Score exact-match of state and ownership per case.
  3. **CONTROL.** On the real windows, shift the ball table by +/- 30 frames (1 s): motion agreement on
     accepted ownership must FALL by >= 20 percentage points (the ball evidence is not decorative).
  4. **PREFIX INVARIANCE.** Output on frames 1..N is byte-identical to the first N rows of the output on
     frames 1..2N (test on a construct; report on 3 real windows).
  5. **REPORT.** Per window and pooled: state shares of F; ownership share of F; motion agreement on
     accepted ownership; abstention reasons (n); the shuffle control; the two WNBA tables as a second
     corpus. `--report` CSV.
  6. CHANGE NOTHING ELSE. No consumer is wired in this row (row 6 of the astra plan owns consumption).

**HONEST LIMITATIONS to state, not discover:** nearest player is not necessarily the handler; a wrong ball
or an airborne ball looks smooth; image-space radii are resolution-dependent (stated scaling); 24 windows +
2 tables are a screening; PASS means proxy-supported, not true possession.

ACCEPTANCE RULE:
  metric        = premise prints; the synthetic score (200 cases); ownership share of F and motion
                  agreement with n per window; the shuffle-control delta; prefix invariance; abstention n
  before        = ball evidence has no downstream reader; no possession state with provenance exists
  bar           = 200/200 synthetic cases correct; 0 cross-cut or stale joins (age > 30 frames never
                  yields OBSERVED_VALID); prefix invariance holds; the shuffle control drops agreement by
                  >= 20 pp (else say the evidence is decorative -- an honest fail); 0 src edits
  n             = 24 windows + 2 tables; 200 synthetic cases; every frame in F
  eye check     = NONE. Say that.
  must not move = `src/`, `data/`, `data/registry/`, every flag, `ball_join.py`, every committed artifact,
                  `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`
  verdict       = **DONE** if the bar holds; **PARTIAL** with the failing item and why.
EVIDENCE: `docs/evidence/tracking/g344_ball_shadow_possession_2026-09-08.md` (<= 60 lines; VERDICT line 1;
tables; NOT VERIFIED; wall time; SHA-256s) + `.../g344_ball_shadow_possession_2026-09-08/states.csv` and
`synthetic.csv` (integer cells zero-padded to 6 digits). **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME
COMMIT** (one `>>` append, LF). **Do NOT edit `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.**
TEST: `tests/platformkit/test_g344_ball_shadow_possession.py`, alone. **NEVER a full pytest.** Every new
file <= 300 lines.
DIVISION OF LABOUR: the codex lane prepares the prereg (sealed alone: radius, motion thresholds, seed, the
window rule), the module, the tests, the synthetic generator and the memo skeleton, and exits `PREPARED
FOR FINISHER` listing the exact commands; it must NOT run the real windows itself (Q1). A missing
`data/registry` or local mirror in the worktree is reported, never a stop.
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
