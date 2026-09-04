GAP G251 | sport basketball (amateur) | worktree a6 | log g251_calibratable_amateur_source
**ACQUISITION AND VERIFICATION ONLY. Change NO production code.** `src/` and `domains/` are READ and
IMPORT only. Use the landed `scripts/platformkit/footage_bridge.py`; build any helper in
`scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (G248 may be running on a5; N=2 is optimal per G200/G216). **Check
first, do NOT interrupt a running row, and say in your memo that you checked and when you began. EXCLUDE
YOUR OWN PROCESS AND YOUR OWN CHECKER COMMAND** -- a G243c dispatch refused on a self-match. The
`track_daemon`, `keep_track_daemon.sh`, `adapter_run` jobs, `inplay_capture_runner` and `foundry_runner`
are PERMANENT residents and the load floor.

**READ THE LANDED G245, G249 AND G250 MEMOS FIRST.**

**WHY THIS ROW EXISTS -- WE NOW KNOW EXACTLY WHAT TO ACQUIRE, AND THE CLIP WE HAVE CANNOT WORK.**
G250 inventoried **20 named physical features across 61 survey frames** of
`basketball__amateur_jh3fnwMi7dM.mp4` and found **ZERO same-frame four-point candidates.** The largest
usable set is **three points, all collinear on the centre line** (best frames 480, 540, 600, 2220). The two
far court corners appear only in other pan states and never co-occur with a fourth nameable unoccluded
point, and **cross-frame combination is invalid because the camera pans.** G249 had already shown **both
near corners are outside the image in 61/61 frames** -- a framing property, not an occlusion one.

**So this source is closed, and it is closed for a reason we can now write down as a purchase order.**

**G250's ACQUISITION CRITERION, WHICH IS THIS ROW'S ACCEPTANCE TEST -- quoted, not reinvented:**
> *"a source camera must show in one frame at least four distinct, named, painted intersections that are
> not occluded and span two dimensions of the court. Practically, it must include some near-side geometry
> (a near corner or visible near painted-end crossing) as well as far-side/centre geometry, rather than
> only a far sideline and centre line. Before any fit, the acquisition review must report the actual
> four-point image quadrilateral area fraction and minimum point-to-other-three line distance, and reject
> a near-zero-spread set."*

THE QUESTION: **can an amateur basketball source that MEETS G250's criterion be found and landed?**

METHOD:
  1. **SCREEN SEVERAL CANDIDATE SOURCES, NOT SECTIONS OF ONE.** G249 already proved that more sections of
     the same camera cannot help, because framing is a property of the camera. **Look for elevated,
     wide or corner-mounted amateur views that show the whole court** -- a high gym-mounted or
     tripod "full court" view is the shape that satisfies the criterion; a courtside coaches camera is
     the shape that failed.
  2. **SCREEN CHEAPLY BEFORE COMMITTING.** For each candidate, pull a **short** section with the proven
     explicit-HLS recipe (a rung like `-f "232+233"` with `--download-sections`; **three prior acquisition
     failures were all selector problems -- if a rung stalls, change the rung, do not wait it out**),
     build a contact sheet, and **first ask the fast visual question: are all four court corners, or at
     minimum some near-side painted geometry, inside the frame?** **Reject on that screen before doing any
     detailed work** -- that single question is what separated the failed source from a usable one.
  3. **APPLY G250's FULL CRITERION TO ANY FINALIST.** On a specific frame, name four distinct unoccluded
     painted intersections, **commit a zoomed identity crop for each with a written statement of what is
     at that pixel**, and **report the quadrilateral area as a fraction of the image and the minimum
     perpendicular distance of any point from the line through the other three.** **Reject a near-zero
     spread.** Do NOT fit a homography and do NOT run a gate -- that is the next row's job.
  4. **LAND ONLY A SOURCE THAT PASSES.** Use the existing `<sport>__<name>.mp4` convention, report full
     identity (exact corpus path, bytes, SHA-256, resolution, frames, fps, duration, source URL, exact
     command), and **end with an `ls -la` of `/workspace/nba-ai-system/data/footage_corpus/` showing the
     file** -- the check whose absence caused G243.
  5. **REPORT EVERY CANDIDATE YOU TRY, KEPT OR REJECTED, WITH THE REASON.** The rejection list is as
     valuable as the acceptance: it tells us how common a calibratable amateur view actually is.
  6. **If no candidate passes, say so plainly and stop.** Report how many sources you screened and what
     each failed on. **"Calibratable amateur views are rare, here is the screen-out rate" is a complete
     and genuinely useful result** about the any-footage goal.
  7. **Do NOT substitute professional footage. Do NOT relax G250's criterion to make something pass. Do
     NOT delete the existing amateur clip** -- it stays as the documented negative case.

**DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE on this pod -- it reports the whole cluster filesystem
against a 50 GB volume cap, and a `Disk quota exceeded` incident followed that misreading. **`dd
conv=fsync` probe before writing, record `du -sm /workspace/nba-ai-system/data` (baseline ~33,081 MB of
50,000), STOP and report if it fails.** Roughly 17 GB is free. **Screening sections should be SHORT -- tens
of MB each -- and rejected candidates must be deleted locally, not uploaded.** **Do NOT delete any corpus
source or the two abandoned partials in `footage_bridge`** (2,490,710,544 and 4,999,500,276 bytes).
**NEVER commit a video -- `data/` is gitignored and must stay untracked.** Delete every temporary artifact
and report bytes freed.

**HONEST LIMITATIONS to state, not discover:** landing a source establishes only that **test material
meeting a geometric criterion exists** -- it says nothing about whether calibration will actually succeed
on it, and nothing about detection or tracking quality. The criterion is **necessary, not sufficient.**
Suitability judgements here are **single-labeller eye judgements** on a handful of frames; eye-label
reliability in this programme has never cleared 80 pct blind agreement on any of four measured criteria,
and **G246 showed repeatable labels can be uniformly wrong.** "Amateur" is a source description, not a
controlled condition. The court model remains assumed, not measured -- **an uncalibrated oblique view
cannot establish 84 versus 94 ft.** Automatic calibration remains 0/17.

ACCEPTANCE RULE:
  metric        = every candidate screened with its outcome and reason; for any finalist, the four named
                  intersections with committed identity crops, the quadrilateral area fraction and the
                  minimum point-to-other-three distance; the full identity of anything landed; and the
                  `ls -la` corpus proof
  before       = G250 found zero same-frame four-point candidates in the existing amateur clip, with a
                 maximum usable set of three collinear centre-line points, and wrote the acquisition
                 criterion this row applies
  bar          = NO pass bar. **A landed source meeting G250's criterion is one full success** and would
                 unblock the first real amateur calibration attempt. **"I screened N sources and none
                 meets the criterion" is an equally full success** and would quantify how rare a
                 calibratable amateur view is. Do not relax the criterion, and do not land a source that
                 fails it.
  n            = every candidate screened -- state the exact count and the screen-out reasons in the
                 verdict line
  eye check    = the contact sheets and identity crops ARE the acceptance evidence
  must not move = G250's criterion, every threshold, bar and verdict, `court_points_for_sport`, the
                  coordinate contract, the harness, existing label files, the 10 existing corpus clips,
                  `src/` and `domains/` (READ and IMPORT ONLY), the pod daemon and keeper, the two
                  abandoned partials
EVIDENCE: docs/evidence/tracking/g251_calibratable_amateur_source_2026-09-04.md with the full candidate
screening table, any finalist's identity crops and conditioning numbers, the full identity and `ls -la`
proof of anything landed, every disk-guard probe, bytes freed, and a NOT VERIFIED list. **ADD A
RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. **`tests/platformkit/test_footage_bridge.py` is the
existing per-file test if you touch the bridge -- run only that file.** NEVER a full pytest. **If a commit
grows an allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME
commit (contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
