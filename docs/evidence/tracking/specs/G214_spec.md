GAP G214 | sport ncaa_basketball / wnba | worktree a5 | log g214_learned_corner_probe_pod
**MEASUREMENT ONLY. Change NO production code.** `src/` is HUMAN-GATED: READ only. Build in
`scripts/platformkit/tracking/`.

**S1 MACHINE: RUN ON THE POD.** Linux, gcc, CUDA, fast network -- **all four of the environmental
blockers that defeated this work locally are absent there.** That is the entire reason for this row.

**DISK GUARD, BINDING -- the pod hit `Disk quota exceeded` tonight and `df` CANNOT see the volume cap**
(it reports the whole cluster filesystem). **Before any checkpoint download, do a small real write test
(`dd` a few MB to a temp path, then remove it) and record `du -sm /workspace/nba-ai-system/data`. If a
write test FAILS, STOP and report -- do not delete anything to make room.** KpSFR's checkpoint is
**714,819,558 bytes**; check headroom before fetching it, and **remove every checkpoint you download
when the row is done**, reporting the bytes you freed. **Never kill, restart or deploy over the pod
daemon or keeper. Delete no corpus source.**

**WHY THIS ROW MATTERS MORE THAN IT DID THIS MORNING.** G207 scored the whole pod body: **32 rows, ZERO
pass, and 29 of 32 fail at `coordinate_contract` before coverage is ever reached**, because output is
in `image_px` which is not scorable for baseball, football or soccer. **Calibration is not depth on one
sport -- it is the gate in front of 91 pct of the entire ledger.** This row is a direct attack on that
gate.

**S3 DEPENDENCY -- the classical route has a measured ceiling and the learned route is untested.**
  - **G210b (landed)**: with the search truncation removed, the real search still scores 0/17, but the
    **ORACLE control is 1/17 with a median max-corner error of 28.841 px**. **So classical's measured
    ceiling on these frames is 1/17 at ~29 px, against G140's 11.39 px p90 label repeatability.**
    (An earlier claim that four approaches "returned zero" was mine, wrong, and RETRACTED -- G210's
    0/17 was a `MAX_GROUPS=24` search artifact.)
  - **G208**: M-LSD scored 0/17, 2/68 recall, 15.59 proposals/frame. **ELSED, DeepLSD, HAWP and KpSFR
    were excluded for ENVIRONMENTAL reasons only** -- no MSVC toolchain, a 30-second window truncating
    a 714 MB download, and HAWP's `easydict==1.13` being LGPL-3.0 (installed, detected, immediately
    uninstalled, correctly).
  - **G205**: classical LSD intersections, 0/17 with 22/68 recall at ~1,928 proposals/frame.
  - **G196**: four HAND-LABELLED corners project correctly, arc landing out-of-sample. **Geometry is
    recoverable; identification is the bottleneck.**
  - **G31** closed a TRAINED calibration path AT LIMIT for tennis. **This row trains NOTHING** -- every
    candidate runs zero-shot on released weights -- so it does not reopen G31.

THE QUESTION, still open: **does any licence-clean zero-shot primitive propose the four paint corners
on these 17 frames?**

CANDIDATES, cheapest first. **Record CODE and WEIGHT licences SEPARATELY, with how each was
established.** G208 found every weight licence unverifiable and that is the gap to close.
  1. **ELSED** (Apache-2.0, no weights) -- builds with gcc; it failed locally only for lack of MSVC.
  2. **M-LSD** -- already measured at 0/17 by G208; **re-run it as a CONTROL** to confirm the pod
     reproduces the local number. A mismatch is itself a finding.
  3. **DeepLSD** and **HAWP** (MIT code; Wireframe-trained weights). **HAWP requires
     `easydict==1.13`, which is LGPL-3.0. Do NOT retain any GPL-family dependency** -- if it cannot be
     avoided, skip HAWP and say so. That is not a failure, it is the licence rail working.
  4. **KpSFR** (MIT, soccer weights) -- run purely to see whether the architecture proposes anything on
     a basketball court. **A null result is expected and still informative.**
  **Do NOT vendor third-party source into this repo. Do NOT add a GPL-family dependency.**

METHOD: G141's protocol exactly. **Reuse `score_frame` from
`scripts/platformkit/tracking/g205_zero_shot_corner_probe.py` unchanged** so every number stays
commensurable with G205, G208 and G210b. One fixed configuration per candidate across all 17 frames,
stated; **no per-frame tuning**. **Report proposals per frame for every candidate** -- G205 measured
~1,928/frame, which no homography solver can consume however good recall gets, so a candidate with
good recall and unusable precision is a NEGATIVE result.

**PREMISES verified by the orchestrator over the whole set (S2):**
`docs/evidence/tracking/g140_corner_targets/corner_pixel_targets.csv` holds 68 rows, all
`status = target`; **all 17 frames carry all FOUR distinct roles** (17 each). Resolutions are
**MIXED**: 12 at 1920x1080, 4 at 1280x720, 1 at 640x360 -- handle that explicitly.

**HONEST LIMITATION to state, not discover:** G140's p90 label repeatability is **11.39 px**, so the
12 px threshold sits at the label noise floor. A pass shows a candidate proposes something in roughly
the right place; it does NOT show production accuracy.

ACCEPTANCE RULE:
  metric        = frames with all four roles within 12 px over 17; per-corner recall over 68;
                  precision over proposals; proposals per frame; per candidate. Plus the M-LSD control
                  against G208's 0/17, 2/68, 15.59.
  before        = classical ceiling 1/17 at ~29 px (G210b oracle); M-LSD 0/17 locally; four candidates
                  never run for environmental reasons
  bar           = **>= 1 of 17 for any candidate.** **STOP: 0 of 17 for every candidate run here,
                  taken with G205, G208 and G210b, closes the ZERO-SHOT corner route AT LIMIT** -- a
                  FULL SUCCESS that would redirect calibration toward labelling or a court-specific
                  trained model (which must cite G31). **It does NOT close labelling.** Do not tune,
                  do not lower the bar, do not add a candidate after seeing results.
  n             = 17 frames (CONSTRUCT, exhaustive) x every candidate obtained; name every exclusion
                  and whether it was environmental or licence-based
  eye check     = render proposals against labels on 5 evenly spaced frames for the best candidate;
                  render the closest one even if every candidate scores 0
  must not move = every threshold, bar and verdict, the 12 px protocol, G205's scorer contract, the
                  coordinate contract, `src/` (READ ONLY), the pod daemon and keeper, the corpus
EVIDENCE: docs/evidence/tracking/g214_learned_corner_probe_pod_2026-09-03.md with the per-candidate
per-frame table, separate CODE and WEIGHT licences and how each was established, package versions and
checkpoint URLs and sizes, proposals per frame, the M-LSD control, the renders, the 11.39 px label
floor, bytes freed after cleanup, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
POD: run there; never kill, restart or deploy over the daemon or keeper.
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
