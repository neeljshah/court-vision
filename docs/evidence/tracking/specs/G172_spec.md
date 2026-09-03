GAP G172 | sport tennis | worktree a5 | log cx_g172_cv2_environment_gap
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it (A2, A7, Q8); self-check section B.
RAILS: read .claude/skills/lane-spawn-rails/SKILL.md and obey its RAILS block, especially
RUNPOD FOR ALL HEAVY WORK -- a local decode was RAM-killed today at 1.4 GB.

THE OPEN QUESTION G169 LEFT. Two runs of the SAME 38 MB tennis clip gave very different output:
  - **G152b, LOCAL**: 28,773 decoded frames, 6,770 rows over **2,597** distinct emitted frames.
  - **`tennis_smoke`, POD**: 1,861 rows over **726** distinct emitted frames.
Both ran BEFORE 09:45:18, so both used the 38 MB clip; the later 2 GB overwrite (G170) is NOT the
explanation and G169's size/hash comparison was made against the swapped file. G169 correctly ruled
out tracker nondeterminism. What it measured and set aside is the live candidate:
**local OpenCV 4.11.0 versus pod OpenCV 5.0.0.**

This matters beyond one clip. A landed memo already records that comparing runs across environments
once invented a defect that did not exist, and a 3.6x gap in emitted frames between environments
would mean **no local measurement is comparable to a pod measurement** -- which is most of the
program's evidence base.

DO THIS, and do the tracking runs ON THE POD:
  (a) Re-establish the premise (Q8). Confirm the two figures above from the committed artefacts, and
      confirm both runs predate 09:45:18. If either is wrong, say so and the row narrows.
  (b) Get the same 38 MB clip decoded under both OpenCV versions and report DECODED frame counts. The
      pod copy at `data/videos/tennis_smoke.mp4` is the 38 MB file; use it. If a local decode is
      needed, subsample and stay under ~300 MB resident.
  (c) The decisive comparison: run the tennis adapter on that clip ON THE POD and report rows and
      distinct emitted frames, then compare against G152b's 6,770 / 2,597. If the pod reproduces
      ~726 again, the gap is environmental and reproducible. **Run it under nohup with a log and
      collect in ONE batched ssh; do not poll.** Use a scratch game id you name in the memo, and do
      NOT overwrite `tennis_smoke`.
  (d) If the gap is environmental, identify WHICH stage differs -- decode, detection, or the two-slot
      emit rule -- by reporting per-stage counts, not just the endpoint. "Environmental, stage
      unknown" is a weaker but honest result; say which you achieved.
  (e) State the consequence for the register: name the landed results that compare a local figure
      against a pod figure, and say which are affected. Do not retract anything yourself; list them.

DO NOT change the adapter, the harness, any threshold, the coordinate contract, or a verdict. Do not
"fix" a version difference by upgrading or downgrading anything on either machine.

ACCEPTANCE RULE:
  metric        = decoded frame counts under both OpenCV versions; pod-side rows and distinct emitted
                  frames for the same clip against G152b's 6,770 / 2,597; per-stage counts if reached
  before        = a 3.6x emitted-frame gap between local and pod on one clip, cause unassigned
  bar           = NO pass bar. Success is the gap reproduced and assigned, or honestly reported as
                  not reproducible. "Not reproducible" would itself be a major finding -- say so.
  n             = >= 1 pod run on the 38 MB clip; state its decoded frame count (CONSTRUCT)
  eye check     = replaced by REPRODUCTION (Q7): every command quoted with raw output
  must not move = the adapter, the harness, every threshold, the coordinate contract, every verdict,
                  and the installed OpenCV on either machine
EVIDENCE: docs/evidence/tracking/g172_cv2_environment_gap_2026-09-03.md with both decode counts, the
pod run, the per-stage table if reached, the affected-results list, and a NOT VERIFIED list. Commit
BEFORE reporting (A7).
TEST: one per-file test only if you add code. NEVER a full pytest.
POD: tracking runs ARE expected here, under nohup, batched collection. NEVER kill, restart or deploy
over the running track daemon or its keeper, and do not stage into data/footage_bridge.
COMMIT: explicit pathspec only, in a5, no push. Report the sha.
NEVER PARK.
