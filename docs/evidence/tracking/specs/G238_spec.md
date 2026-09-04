GAP G238 | sport wnba | worktree a6 | log g238_homography_inlier_census
**MEASUREMENT ONLY. Change NO production code.** `src/` is HUMAN-GATED: **READ and IMPORT only.** You may
instrument **inside your own process** (wrap, trace, or monkey-patch a callee to observe); **write no
byte into `src/` and deploy nothing to the pod checkout.** Build in `scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (G236 may be running; N=2 is the measured optimal schedule per
G200/G216). **Check first and say in your memo that you checked and when you began.** The
`track_daemon`, `keep_track_daemon.sh`, `adapter_run` jobs, `inplay_capture_runner` and `foundry_runner`
are PERMANENT residents and the load floor -- never wait for them, never kill or restart them.

**WHY THIS ROW EXISTS -- IT SETTLES, CHEAPLY, WHETHER TEN ROWS OF CALIBRATION WORK WERE AIMED AT THE
WRONG THING.**

Two findings landed tonight, both from reading rather than measurement, and together they suggest the
basketball court model is anchored to a foreign court on an almost-degenerate match:

  - **G237-PANO-GENERIC (measured):** all six "per-clip" cached panoramas in `resources/panos/` are
    **byte-identical** to `resources/pano_enhanced.png` -- one md5 `408aca74842f9cd4a1be094d0610230d`
    across football, ncaa_basketball, soccer and three WNBA clips, all `(500, 3698, 3)`. The per-clip
    build cannot pass `_pano_valid` (`:843-851` demands >=2000 px wide and a 3.0-50.0 aspect ratio; a
    broadcast frame is ~1.88:1), so the generic fallback is used. The comment at `:884-888` says this is
    deliberate because **`M1` (`Rectify1.npy`) is calibrated for the Short4Mosaicing panorama.**
  - **G237-INLIER-FLOOR (inference):** `_H_MIN_INLIERS = 5` (`:351`), and the comment at `:889` states
    **'Broadcast frames give 5-7 SIFT inliers vs pano_enhanced -- _H_MIN_INLIERS=5 ensures these are
    accepted rather than falling back to stale EMA.'** Five is one above the four-point minimum: no
    redundancy to reject a bad sample.

**IF THE INLIER COUNTS REALLY SIT AT 5-7 IN PRODUCTION, then per-frame corner detection was never the
binding constraint and G194's "DEGENERATE basketball projection" is the design's expected output. IF
THEY ARE HEALTHY -- say 30+ -- then my synthesis is WRONG, the anchoring is working better than the
comments suggest, and I want to know that immediately.**

THE QUESTION: **what is the actual distribution of SIFT inlier counts in `_get_homography` on a real
basketball run, and which of its three acceptance tiers do frames land in?**

METHOD:
  1. **Instrument `_get_homography` (`unified_pipeline.py:1230`) from your own process** -- wrap it, or
     wrap the matcher it calls -- to record per invocation: **the inlier count, the total match count,
     which tier fired (reject below `_H_MIN_INLIERS`, EMA blend, or hard reset above
     `_H_RESET_INLIERS`), and whether an `M` was ultimately installed.** **Do not change any threshold.**
     Report the values of `_H_MIN_INLIERS` and `_H_RESET_INLIERS` you observed at runtime.
  2. **Run one bounded basketball clip.** **Choose an invocation known to reach the frame loop.** Two
     warnings from tonight, both measured: `run_clip.py --frames 1200 --no-show --skip-features` made 400
     detector calls and emitted ZERO rows (G211b), and 9 of 9 historical basketball daemon jobs died in
     `_build_court` (G234, G234-COMPLETE) -- though G235 found that crash does NOT always reproduce.
     **If the route dies or emits nothing, report that and say which failure you hit; do not retry it
     more than twice.**
  3. **Report the inlier distribution: min, p10, median, p90, max, and the count of invocations in each
     tier.** **The DISTRIBUTION is the deliverable, not a mean.**
  4. **Also confirm which panorama the run actually used** -- log the shape and, if cheap, the md5 of
     the array `_load_pano` returned, and say whether it was a cache hit, a per-clip build, or the
     general fallback. **That closes the one gap in G237-PANO-GENERIC, which inferred the fallback from
     identical cache files rather than observing the code path.**
  5. **State plainly whether G237-INLIER-FLOOR survives.** **"Inliers are healthy and my synthesis is
     wrong" is a FULL SUCCESS and is the more valuable outcome**, because it would stop the programme
     redirecting on a bad inference. Say which it is, with the numbers.
  6. **Do NOT propose a fix, do NOT change a threshold, and do NOT draw a conclusion about what the
     coordinates mean.** This row measures one distribution and one code path.

**DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE on this pod (it reports the whole cluster filesystem
against a 50 GB volume cap; a `Disk quota exceeded` incident followed that misreading). **`dd conv=fsync`
probe before writing, record `du -sm /workspace/nba-ai-system/data` (baseline ~32,200 MB of 50,000), STOP
and report if it fails.** Write to a NEW directory, delete every temporary artifact and report bytes
freed, and **delete no corpus source and no legacy table.**

**HONEST LIMITATIONS to state, not discover:** one clip and one bounded run on a shared,
NON-DETERMINISTIC route (G190/G195/G198/G203) -- a single distribution is one draw, and G235 showed this
path's behaviour varies between runs. Instrumenting from outside observes what the code does on THIS
run; it does not prove the historical rows were produced the same way. An inlier count is a property of
the match, not evidence that the resulting coordinates are right or wrong.

ACCEPTANCE RULE:
  metric        = per-invocation SIFT inlier and match counts summarised as min/p10/median/p90/max; the
                  count of invocations in each of the three acceptance tiers; the runtime values of
                  `_H_MIN_INLIERS` and `_H_RESET_INLIERS`; and the panorama actually used (shape, source
                  path, cache-hit vs built vs general fallback)
  before        = `_H_MIN_INLIERS = 5` and a source comment claiming 5-7 inliers are typical; all six
                  per-clip panorama caches are byte-identical to the generic one; NEITHER has been
                  observed at runtime, and the root-cause synthesis rests on that inference
  bar          = NO pass bar. **"Inliers are healthy, so the synthesis is wrong" is a FULL SUCCESS and
                 the more useful answer.** Change no threshold, propose no fix, and do not tune the run
                 to produce a particular distribution.
  n            = one bounded run on one clip; report the invocation count as the denominator
  eye check    = none; this row is counts
  must not move = `_H_MIN_INLIERS`, `_H_RESET_INLIERS`, every other threshold, bar and verdict, the
                  coordinate contract, the harness, `src/` (READ and IMPORT only -- no writes, no
                  deploys), the pod daemon and keeper, the corpus, the legacy tables
EVIDENCE: docs/evidence/tracking/g238_homography_inlier_census_2026-09-04.md with the instrumentation
method, the inlier and match distributions, the tier counts, the observed threshold values, the panorama
identity and how it was obtained, an explicit verdict on whether G237-INLIER-FLOOR survives, every
disk-guard probe, bytes freed, the load context, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
