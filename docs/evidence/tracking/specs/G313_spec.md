GAP G313 | sport all | worktree a12 | log g313_ten_id_cap
**TRACE + CONSTRUCT ROW. `src/`, `domains/`, `api/`, `kernel/` and `intel/` are READ and IMPORT
only -- the id assignment path is HUMAN-GATED. You may READ, IMPORT and RUN it; you may NOT edit
it. Build in `scripts/platformkit/`. If the cause sits in `src/`, the deliverable is a PROPOSED
diff file, NOT an edit, and the row STOPS there for a human to apply.**

**WHERE THIS ROW RUNS:** LOCAL. The premise reproduction reads pod `tracking_data.csv` files
fetched READ-ONLY by `scp` into a scratchpad -- **never into `data/` in the repo.** **NEVER stop,
signal or interfere with `track_daemon`.** No GPU, no GPU lease.

**WHY THIS ROW EXISTS.** G309 measured that **every one of the 13 completed games reports EXACTLY
10 distinct `player_id` values** -- across five sports (nba, wnba, ncaa_basketball, basketball) and
two source resolutions (720p and 1080p), over row counts from 1,653 to 6,623 and emitted-frame
counts from 482 to 1,000. **A uniform id count that is invariant to sport, resolution, clip length
and row count is a CAP or a re-use policy, not a measurement of how many people were on screen.**
G309 asserted no cause. Until the cause is named, `distinct_track_ids`, `id_churn_per_detection`
and `median_track_len_rows` are all reading a constant, and any re-identification claim built on
them is reading the same constant back.

**PREMISE (step 0, BINDING before-condition):** on **3** censused games fetched from the pod,
count the distinct `player_id` values in `tracking_data.csv` and **PRINT the three counts.** **If
any of the three is not exactly 10, the premise is FALSE: STOP, write the memo, commit, and report
PREMISE FALSE** -- a cap that does not reproduce on a fresh read is a census artifact, not a defect.

METHOD:
  1. **TRACE THE CAUSE, READ-ONLY.** Follow the id assignment path from `scripts/run_clip.py`
     through `src/pipeline/unified_pipeline.py` into `src/tracking/`. Candidate mechanisms to
     confirm or eliminate, each by reading the code and NOT by guessing: a fixed track budget or
     slot pool, an OSNet re-identification gallery size, a top-N detection cut before association,
     a Hungarian cost matrix sized to a constant, or an explicit id re-use policy.
     **NAME THE CAUSE AS `file:line`.** If more than one mechanism could produce 10, name each and
     say which one the construct actually fires.
  2. **CONSTRUCT TEST** in `scripts/platformkit/` that **reproduces the cap on SYNTHETIC
     detections**: feed the traced component more than ten simultaneous, well-separated, unambiguous
     detections and show that the distinct id count saturates at 10. **The construct is the proof
     the trace is right** -- a trace with no reproduction is a hypothesis.
  3. **IF THE FIX IS IN `src/`: WRITE THE PROPOSED DIFF AND STOP.**
     `docs/research/organization-sprint/PROPOSED-<name>-2026-09-07.md` (local-only), carrying the
     exact change and the exact reason. **Apply NOTHING.** If the fix is entirely inside
     `scripts/platformkit/`, it may be made there.
  4. **CHANGE NOTHING ELSE.** No threshold, no production default, no register edit, no adoption.

**HONEST LIMITATIONS to state, not discover:** **naming the cause is NOT fixing it, and fixing the
cap is NOT improving tracking.** Lifting a ten-id ceiling can raise the id count while lowering
identity quality; this row measures neither recall, precision, identity accuracy nor registration,
and says so in those words. Image space only. All 13 games are `passed = false`. **A construct that
saturates at 10 proves the mechanism EXISTS; it does NOT prove it is what produced the 10 in every
pod game** -- state which games were traced end to end and which were only counted.

ACCEPTANCE RULE:
  metric        = the three printed distinct-id counts; the cause as `file:line`; the construct's
                  saturated id count
  before        = 13/13 completed census games at exactly 10 distinct `player_id` values, cause
                  NOT traced to source anywhere in the programme (G309 says so explicitly)
  bar           = the cause is named with a `file:line`, the construct **reproduces 10/10** given
                  more than ten unambiguous synthetic detections, and either a PROPOSED diff file
                  exists or the fix is demonstrably confined to `scripts/platformkit/`
  n             = 3 pod games (premise) + 1 synthetic construct
  eye check     = NONE. No frames, no renders, no labels. Say that rather than implying validation.
  must not move = `data/tracking/` on the pod (READ ONLY); the running `track_daemon`; `src/`,
                  `domains/`, `api/`, `kernel/`, `intel/`; `tracking_harness.py`; every threshold
EVIDENCE: `docs/evidence/tracking/g313_ten_id_cap_2026-09-07.md` (<= 60 lines) with the three
counts, the `file:line`, the construct result, the proposed-diff path if any, and a **NOT
VERIFIED** list. **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT** (one `>>` append). **Do NOT
edit `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`** -- the orchestrator owns it.
TEST: `tests/platformkit/test_g313_ten_id_cap.py` -- the synthetic construct of step 2.
**n = 1 (CONSTRUCT).** Run that ONE file. **NEVER a full pytest.**
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first. **NEVER PARK.**
