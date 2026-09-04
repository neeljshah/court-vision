GAP G220c | sport ncaa_basketball / soccer (amateur tier) | worktree a4 | log g220c_amateur_footage_working_rung
**ACQUISITION AND CLASSIFICATION ONLY. Change NO production code.** `src/` is HUMAN-GATED: READ only.
`scripts/platformkit/footage_bridge.py` is READ ONLY -- reuse its constants and helpers, **do not edit
it.** Build in `scripts/platformkit/tracking/`.

**READ `docs/evidence/tracking/specs/G220_spec.md` and its landed memo FIRST.** This row inherits
G220's candidate list, budget discipline, disk guards, rubric and honesty requirements unchanged. **Two
of my own explanations for G220's failure have already been withdrawn (G220-CAUSE-RETRACTION, then the
G220b premise falsification). The third is REPRODUCED and is what this row acts on.**

**WHY G220 GOT ZERO, NOW PROVEN HEAD-TO-HEAD (G220-CAUSE-FOUND).** On candidate `jh3fnwMi7dM`:

    -f "b[height<=1080][height>=720]"                      -> ERROR: Requested format is not available
    -f "bv*[height<=720][vcodec^=avc1]+ba/b[height<=720]"  -> SELECTED 136+251 1280x720

**`-F` shows the video DOES carry 720p and 1080p -- formats 232 (1280x720 m3u8), 136 (1280x720 dash),
270 (1920x1080 m3u8) -- but every one is listed `video only`.** `b[...]` selects the best MUXED
video+audio stream, and no muxed stream reaches 720p; muxed tops out at 640x360. **The second rung
succeeds because `bv*+ba` merges a video-only stream with a separate audio stream.** **So the footage
was always obtainable and my G220 spec simply told the lane to use a rung that cannot work on modern
YouTube.**

**THE CANDIDATES ARE UNCHANGED -- use THESE SIX and never a substitute**, so what lands is what was
reviewed. An id that no longer resolves, is region-blocked or age-gated is a NORMAL outcome: record it
with the error and move on.

    | youtube id | duration s | listed height | what it is | gap category targeted |
    |---|---:|---:|---|---|
    | `jh3fnwMi7dM` | 8845 | 1080 | Coaches Camera, Lorain vs Bedford HS boys varsity | **fixed camera + amateur/HS** |
    | `qpZfGp_fScU` | 4190 |  720 | Bismarck HS varsity at Dickinson, full game | amateur/HS |
    | `1MwO3CDkeeM` | 1858 | 1080 | Bremen at Triton, 5th grade boys | amateur, youth, likely dim gym |
    | `3asBuhRd_LI` | 1772 | 1080 | Pella 8th grade boys vs Newton (main gym) | amateur, youth, school gym |
    | `lAs8JaoWNwg` | 4770 |  720 | GACS mens soccer, sideline camera | **fixed camera + amateur, soccer** |
    | `XwpLBtt1G2g` | 3869 | 1080 | Nepean Hotspurs U15-16, full match | amateur youth soccer |

METHOD:
  1. **Use a MERGING format selector.** Start from the bridge's own working rung
     `bv*[height<=720][vcodec^=avc1]+ba/b[height<=720]`. **Report, per candidate, the selector used, the
     format ids actually selected, and the height actually obtained.** **A 360p result must be reported
     as a failure of this row, not quietly accepted** -- 720p is demonstrably available.
  2. **Bounded slices, not whole games.** Either request a 16-minute section as `plan_section`
     (`footage_bridge.py:308-318`) computes it, or -- if sections still fail -- download whole and cut a
     bounded slice LOCALLY with `ffmpeg -ss/-t -c copy`, then upload ONLY the slice. **Say which route
     each candidate took and why.**
  3. **BINDING BUDGET, stop at it rather than negotiating:** at most ONE ~16-minute slice per candidate;
     **LOCAL download cap 20,000 MB**; **POD upload cap 4,000 MB**; running totals checked after every
     clip. **Delete local whole-file downloads once their slice exists and report bytes freed both
     locally and on the pod.**
  4. **DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE on this pod (it reports the whole cluster
     filesystem against a 50 GB volume cap; a `Disk quota exceeded` incident followed that misreading).
     **`dd conv=fsync` probe before and after each upload, record
     `du -sm /workspace/nba-ai-system/data` (baseline ~31,960 MB of 50,000), STOP and report if a probe
     fails -- do not delete anything to make room.**
  5. **Do NOT resume the general acquisition loop, the watchdog, or the bridge supervisor. Never kill,
     restart or deploy over the daemon or keeper.** Bound every external command with a timeout so a
     hang is RECORDED rather than parked -- G220 did this well and it is why its null result was
     trustworthy.
  6. **Run `footage_content_gate.py` on each acquired slice and report its verdict**, saying explicitly
     that it is an ingest decision only and **must never touch a metric denominator**, per its own
     module docstring.
  7. **Classify each slice against G213's rubric unchanged**, from **5 evenly spaced single-frame
     seeks**, never a full decode. Commit the frames, downscaled.
  8. **Then answer the question this line of work exists for: which of G213's ZERO-representation
     categories now have at least one example, and which are STILL zero?** Quote G213's list exactly --
     zero handheld game-camera; zero fixed **single-camera** game footage (tennis's fixed-wide broadcast
     explicitly does NOT count); zero **amateur/high-school direct field/court camera acquisition** (the
     corpus's one amateur item is a desktop-commentary screen capture, not a game camera); zero
     graphics-free; zero high surface visibility; zero dim-gym. **"We fetched six clips and the corpus is
     still monolithic" is a FULL SUCCESS if that is what the frames show** -- for instance if "Coaches
     Camera" turns out to pan after all.
  9. **These are single-labeller eye judgements with no second labeller, exactly as G213's were. Say
     so.** Where a clip is ambiguous, say ambiguous. **Do not infer capture style from the title.**

**DO NOT track these clips, run the route on them, add them to any tracking queue, or draw any tracking
conclusion.** That is later work needing a quiet pod.

ACCEPTANCE RULE:
  metric        = per candidate: selector used, format ids selected, height obtained, route taken
                  (section or local-slice), bytes local and uploaded against both caps, disk-guard probe
                  results, content-gate verdict, G213-rubric classification; plus the updated
                  zero-representation list beside G213's
  before        = G220 acquired ZERO because my spec pinned a muxed >=720p rung YouTube does not serve;
                  G220b was CLOSED AT LIMIT on a falsified premise; G213's zero list is unchanged and no
                  robustness claim about arbitrary footage is supportable
  bar           = NO pass bar. **At least one clip credibly classified as an amateur GAME CAMERA or a
                  fixed SINGLE camera would close a category that is currently empty. Closing none,
                  honestly reported, is also a full success.** Do not stretch a classification, and do
                  not accept 360p silently.
  n             = 6 reviewed candidates (CONSTRUCT, exhaustive; no substitutions) x 5 frames each
  eye check     = the classification IS the eye check; commit the frames
  must not move = every threshold, bar and verdict, the coordinate contract, `src/` (READ ONLY),
                  `footage_bridge.py` (READ ONLY), the pod daemon, keeper, bridge supervisor and
                  watchdog, the existing corpus (delete NOTHING)
EVIDENCE: docs/evidence/tracking/g220c_amateur_footage_working_rung_2026-09-04.md with the per-candidate
table, selectors and heights, both running byte totals, every disk-guard probe, the content-gate
verdicts, the committed frames, the rubric classification, the updated zero-representation list, bytes
freed, an explicit statement that classifications are single-labeller judgements, and a NOT VERIFIED
list. Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
