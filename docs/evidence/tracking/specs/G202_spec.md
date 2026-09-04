GAP G202 | sport wnba / ncaa_basketball | worktree a3 | log g202_basketball_selection_census
**HOLD LIFTED AND THE DETERMINISM QUESTION IS SETTLED -- AMENDED 2026-09-04 BY THE ORCHESTRATOR.**
The original hold said to wait for G198 and to run under whatever determinism configuration it
established. **G198 has reported, and so have G190, G195, G199 and G203. NO DETERMINISTIC MODE EXISTS.**
G203 eliminated the last enumerated candidate by showing decode is byte-identical -- 1,200 frame hashes
per run across three fresh processes, zero differences -- so **the route consumes identical pixels in
identical order and its output still differs, with no identified source.** **Therefore this spec's own
stated fallback is now BINDING: run n=3 per configuration and report DISTRIBUTIONS, never a single
number.** Do not spend this row hunting determinism; that search is separately funded and has consumed
six rows. **Report the spread across your three runs as a first-class result** -- if survivor counts
vary widely between identical runs, that variance is itself a finding about how repeatable any quality
number on this route can be.

**MEASUREMENT ONLY for the census half. Change NO production code in `src/`** -- human-gated, READ and
wrap in your own process only. Deploy nothing into the pod checkout (B5).

**S1 MACHINE: RUN ON THE POD.** RTX 3090.

**S3 DEPENDENCY, and this row exists because a previous framing was WITHDRAWN.**
Fable's adjudication (`G_ADJUDICATION_fable_review_2026-09-03.md:44-51`) established, and the
orchestrator re-read to confirm: at source frame 474, where roughly ten players are visible, **the raw
detector emitted 15 person boxes, three times out of three, and the route kept 2 or 3.** G188: 6
on-court players retained from 11 raw. **"The detector is emitting spectators" was withdrawn as
externalisation** -- a person detector is supposed to emit every person; **the SELECTOR is supposed to
keep players, and the selector is ours.**

WHY THIS IS THE FIRST ROW THAT COULD LEGITIMATELY PASS ANYTHING. Per
`TRACKING_TARGET_SPEC_2026-09-03.md`: `team_spacing` is a convex hull over a team and needs five
players. **At 2-3 survivors a hull has zero area**, which is precisely the `team_spacing == 0.0` that
`feature_engineering.py:92` scrubs as "invalid hull area". So thin coverage does not degrade the
primary spacing feature, it makes it UNDEFINED. `min_players = 6` for basketball encodes the same
requirement.

**SECOND AMENDMENT 2026-09-04 -- YOUR BASELINE IS STALE AND YOU MUST RE-MEASURE IT, NOT INHERIT IT.**
The "15 raw boxes, 2-3 survivors" observation predates TWO production defects that were found and fixed
on 2026-09-03, both of which sit directly on the selection path:
  1. **`src/tracking/osnet_reid.py` was running re-identification on an UNTRAINED network.** When the
     OSNet load failed, a broad handler installed `mobilenet_v2(weights=None)` -- randomly initialised --
     set `available = True`, and emitted no signal. Fixing it made re-ID **6.8x faster** (0.103 s ->
     0.0152 s for 17 crops), which is itself evidence the fallback was live. **Appearance embeddings
     used for player association were therefore NOISE at the time frame 474 was observed.**
  2. **`src/tracking/ball_detect_track.py` was resolving to a generic COCO `yolov8n.pt`** rather than the
     fine-tuned ball model, by the same silent-substitution shape.
  Root cause of both: `data/` and `models/` are gitignored, so the git-archive deploy carried no weights.
  G218 has since classified 19 handlers of this shape, 18 of them on the tracking hot path.

**So "15 raw, 2-3 survivors" may already be OBSOLETE. Re-measure it as the FIRST thing you do and report
the current number beside the historical one.** **If survivors have improved, say so plainly -- that is a
real result and it would mean a production defect, not the selector, was the dominant cause.** If they
have not, the census proceeds as written and is now measured on a route whose re-ID actually works.
**Do NOT quote the historical 2-3 as current.** **A11: record the SHA-256 of the deployed
`osnet_reid.py`, `ball_detect_track.py` and their weight files, so a later reader can tell which side of
the fix your run is on.**

PART 1 -- THE CENSUS (this is the deliverable; do this first and completely):
  Instrument in your own process to record, per frame, over a bounded run:
    a. raw detector box count;
    b. how many survived to the emitted table, and **at which stage each dropped** -- name the stages
       from the code rather than guessing, and report an exhaustive per-stage attribution so the
       counts add up;
    c. for a sample of dropped boxes, whether they were on-court players or not.
  **Report the whole-run DISTRIBUTION of raw and survivor counts (S2), not frame 474 alone.** Frame
  474 is one anecdote and this row exists because anecdotes were over-read.
  **Name the ELIGIBLE DENOMINATOR explicitly**: attempted gameplay frames, never `--frames`.

PART 2 -- TWO BOUNDED PROBES, each measured against Part 1's baseline, each reported separately:
  (i) `yolo_imgsz` at 960 and at 1280 against the current 640 (`unified_pipeline.py:1007` comments
      that players are about 25 px at 640). Set it through config in YOUR OWN process; do not edit
      `src/`. Report raw and survivor counts and wall time at each size.
  (ii) A polygon filter on projected feet, as a POST-HOC filter in your own analysis over the emitted
      rows. **You cannot do this honestly for basketball unless a valid court polygon exists** --
      G194 measured the basketball projection as DEGENERATE, so projected feet are meaningless
      through the production path. **If you cannot obtain a valid per-clip homography, SKIP (ii),
      say why, and report Part 1 and (i) only.** Do NOT substitute an image-space box as if it were a
      court polygon; that is a different filter with a different meaning.

**DO NOT change any threshold, `conf`, `min_players`, or any gate value to improve a count.** The
deliverable is an attribution of where players are lost, not a better number.

**A9:** `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4`, 2,931,985,407 bytes,
1920x1080, 174,430 frames. `--frames 1200 --no-show --skip-features`.
**A11:** pod SHA-256 for `unified_pipeline.py` and `advanced_tracker.py`.
**B11:** the route is non-deterministic -- n=3 minimum per configuration unless G198 established a
deterministic mode, in which case use it and SAY SO.
**B13/Q9:** per-frame and per-stage records in the artifact.

ACCEPTANCE RULE:
  metric        = whole-run distribution of raw boxes and survivors; exhaustive per-stage drop
                  attribution; raw/survivor counts and wall time at imgsz 640 / 960 / 1280
  before        = the raw detector emits about 15 person boxes where about 10 players are visible and
                  the route keeps 2-3; WHERE the other boxes are lost is unattributed
  bar           = NO pass bar. **"The losses are attributed to stage X" is the success.** A probe that
                  does NOT improve survivor counts is a full success and must be reported as such --
                  it retires an option. Do not tune to make a probe look good.
  n             = one clip, bounded run, n=3 per configuration (or 1 if a deterministic mode exists)
  eye check     = for 3 evenly spaced frames, render raw boxes and survivors side by side and state
                  whether the dropped boxes were on-court players
  must not move = every threshold, `conf`, `min_players`, every bar and verdict, the coordinate
                  contract, `src/` (READ ONLY), the pod daemon and keeper, the corpus (delete NOTHING)
EVIDENCE: docs/evidence/tracking/g202_basketball_selection_census_2026-09-03.md with the distribution,
the per-stage attribution, the probe table, the renders, and a NOT VERIFIED list. Commit BEFORE
reporting (A7).
TEST: a per-file test for any harness added under `scripts/platformkit/tracking/`, pasted. NEVER a
full pytest. **If a commit grows an allowlisted file, raise its entry in
`tests/platformkit/test_loc_rail_scope.py` in the SAME commit (contract A12) and run that rail test.**
POD: run there. Never kill, restart or deploy over the daemon or keeper.
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
