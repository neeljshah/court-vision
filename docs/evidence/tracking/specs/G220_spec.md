GAP G220 | sport ncaa_basketball / soccer (amateur tier) | worktree a2 | log g220_amateur_footage_acquisition
**ACQUISITION AND CLASSIFICATION ONLY. Change NO production code.** `src/` is HUMAN-GATED: READ only.
Build in `scripts/platformkit/tracking/`. You may READ `scripts/platformkit/footage_bridge.py` and
reuse it; **do not edit it.**

**HELD -- DO NOT START THE DOWNLOAD UNTIL G216 HAS REPORTED.** G216 is measuring read throughput from
`/workspace` against local storage on the pod, and **an upload running during it would corrupt exactly
the number it exists to produce.** Check first (`ps` on the pod for concurrent route jobs, and the
G216 ledger row) and **say in your memo that you checked and when you started.** Preparation work --
reading code, writing the harness, writing tests -- may proceed immediately.

**WHY THIS ROW EXISTS -- THE PROGRAMME'S STATED GOAL IS ARBITRARY-FOOTAGE TRACKING AND THE CORPUS
CANNOT SUPPORT A SINGLE ROBUSTNESS CLAIM ABOUT IT.** G213 visually classified every corpus clip and
found the corpus **MONOLITHIC**. **Quote G213's zero list EXACTLY as it is written, because it is more
precise than a loose summary and your comparison must be against the real baseline:** zero handheld
game-camera footage; zero fixed **single-camera** game footage (tennis is a multi-camera broadcast that
merely uses a fixed-wide primary play view, which G213 explicitly says does NOT count); zero
**amateur/high-school direct field/court camera acquisition** (the corpus DOES contain one
amateur/home-produced item, but it is a **desktop-commentary screen capture, not an amateur game
camera**); zero graphics-free footage; zero high playing-surface visibility; and zero dim-gym or
visibly poor lighting. **That census covered 13 clips.** **So the missing thing is specifically an
AMATEUR GAME CAMERA POINTED AT A COURT OR FIELD -- not "amateur footage" loosely.** Nearly every
measurement in the tracking body (G189, G190, G193, G195, G198, G203) ran on ONE clip,
`wnba__wnba_01.mp4`. **So every claim about robustness to "any footage" is currently unsupported by
construction, and that is the gap this row closes.**

**THE VOLUME LESSON FROM TONIGHT, which this row must not repeat.** Acquisition was PAUSED because it
outran tracking by roughly 7x and filled the 50 GB volume; 8,724 MB of redundant duplicate `.part`
files had to be deleted by hand. **The corpus is monolithic AND huge because acquisition fetches whole
broadcasts. Diversity does not require whole games.** `footage_bridge.py` already supports bounded
section downloads (`SECTION_MINUTES = 16`, `plan_section` at :308) and its own comments record that
sections made fetching **~12x cheaper** and that **with cookies a section of an HLS stream fetches only
the segments it needs** -- measured at 5.58 MiB in 2 seconds for a 20-second slice. **Use sections. Do
not fetch a whole game.**

**RESOLUTION IS NOT A FREE VARIABLE -- the bridge's own comments record a controlled re-run
(`tennis_resolution_controlled_2026-09-01.md`) in which raising resolution moved frames reaching the
court's five-line gate from 5.0 pct to 18.7 pct and cut severe line under-detection from 36.7 pct to
8.5 pct.** Section downloads without cookies force `player_client=web`, which exposes exactly one
non-storyboard format, **itag 18 at 640x360**. **Fetch at 720p or better and RECORD the height you
actually got for every clip.** A 360p acquisition would confound any later comparison against the
broadcast corpus and must be reported as a failure of this row, not quietly accepted.

**THE CANDIDATES ARE ALREADY SEARCHED AND VERIFIED -- the orchestrator resolved each through
`yt-dlp --skip-download` on 2026-09-04, so each id existed and returned metadata at that time. Use
THESE and do not substitute others**, so that what lands is what was reviewed:

    | youtube id | duration s | height | what it is | gap category targeted |
    |---|---:|---:|---|---|
    | `jh3fnwMi7dM` | 8845 | 1080 | Coaches Camera, Lorain vs Bedford HS boys varsity | **fixed camera + amateur/HS** |
    | `qpZfGp_fScU` | 4190 |  720 | Bismarck HS varsity at Dickinson, full game | amateur/HS |
    | `1MwO3CDkeeM` | 1858 | 1080 | Bremen at Triton, 5th grade boys | amateur, youth, likely dim gym |
    | `3asBuhRd_LI` | 1772 | 1080 | Pella 8th grade boys vs Newton (main gym) | amateur, youth, school gym |
    | `lAs8JaoWNwg` | 4770 |  720 | GACS mens soccer, sideline camera | **fixed camera + amateur, soccer** |
    | `XwpLBtt1G2g` | 3869 | 1080 | Nepean Hotspurs U15-16, full match | amateur youth soccer |

**A candidate that no longer resolves, is region-blocked or is age-gated is a NORMAL outcome: record it
as unavailable with the error and move on. Do NOT search for a replacement** -- an unreviewed
substitute is how an unvetted clip enters the corpus.

**BINDING BUDGET, and you must stop at it rather than negotiating with it:**
  - **At most ONE 16-minute section per candidate. Six sections total.**
  - **HARD TOTAL CAP: 4,000 MB across the whole row.** Check the running total after every clip and
    **STOP at the cap even if candidates remain**, reporting what you skipped.
  - **DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE on this pod -- it reports the whole cluster
    filesystem against a 50 GB volume cap, and that misreading caused tonight's `Disk quota exceeded`.
    **Before and after each clip, do a real `dd` write probe of a few MB and record
    `du -sm /workspace/nba-ai-system/data`.** Baseline at allocation was **30,757 MB of 50,000**.
    **If a write probe fails, STOP immediately and report -- do not delete anything to make room.**
  - **Do NOT resume the general acquisition loop, the watchdog, or the bridge supervisor.** This is a
    one-shot targeted fetch. **Never kill, restart or deploy over the pod daemon or keeper.**
  - **Delete every `.part` file your own run leaves behind and report the bytes freed.** The bridge
    left duplicate `.part` twins of completed transfers tonight; do not add more.

METHOD:
  1. Reuse `footage_bridge.py`'s existing section and format machinery rather than writing a new
     downloader. **State which rung each clip actually landed on and the resulting height.**
  2. Acquire one bounded section per candidate, within the budget above.
  3. **Run the existing `footage_content_gate.py` on each clip and report its verdict.** It is
     fail-open and is an ingest decision only -- **say explicitly that it must never touch a metric
     denominator**, which is its own module docstring's rule.
  4. **Classify each acquired clip against G213's rubric, using G213's categories unchanged** -- camera
     style, production tier, overlay, surface visibility, surface appearance, lighting -- from **5
     evenly spaced single-frame seeks** (`ffmpeg -ss ... -frames:v 1`), never a full decode. Commit the
     frames, downscaled.
  5. **Then answer the only question that matters for this row: which of G213's ZERO-representation
     categories now have at least one example, and which are STILL zero?** Put your table beside
     G213's. **"We fetched six clips and the corpus is still monolithic" is a FULL SUCCESS and must be
     reported plainly if that is what the frames show** -- for instance if every clip turns out to be
     well-lit, or if "Coaches Camera" turns out to pan after all.
  6. **These are single-labeller eye judgements with no second labeller, exactly as G213 was. Say so.**
     Where a clip is ambiguous, say ambiguous rather than forcing a category, and **do not infer
     capture style from the title** -- a title saying "Coaches Camera" is a hypothesis, and the frames
     are the evidence.

**DO NOT track these clips, run the route on them, or draw any tracking conclusion.** Whether the
tracker degrades on amateur footage is the NEXT row and needs a quiet pod; this row establishes that
we HAVE such footage and what it looks like. **Do not add these to any tracking queue.**

ACCEPTANCE RULE:
  metric        = per-candidate outcome (acquired / unavailable with the error), bytes and height for
                  each, running total against the 4,000 MB cap, content-gate verdict, the G213-rubric
                  classification per clip, and the updated zero-representation list beside G213's
  before        = the corpus is monolithic: professional broadcast with a moving camera, ZERO amateur,
                  ZERO fixed-camera and ZERO dim-gym examples, so no robustness claim about arbitrary
                  footage is supportable
  bar           = NO pass bar. **At least one clip credibly classified as fixed-camera or amateur would
                  close a category that is currently empty. Closing none, honestly reported, is also a
                  full success** -- it would say this footage tier is harder to obtain than assumed.
                  Do not stretch a classification to close a category.
  n             = 6 reviewed candidates (CONSTRUCT, exhaustive; no substitutions) x 5 frames each
  eye check     = the classification IS the eye check; commit the frames
  must not move = every threshold, bar and verdict, the coordinate contract, `src/` (READ ONLY),
                  `footage_bridge.py` (READ ONLY), the pod daemon, keeper, bridge supervisor and
                  watchdog (leave every one as you found it), the existing corpus (delete NOTHING)
EVIDENCE: docs/evidence/tracking/g220_amateur_footage_acquisition_2026-09-04.md with the per-candidate
table, heights and rungs, the running byte total against the cap, every disk-guard probe result, the
content-gate verdicts, the committed frames, the rubric classification, the updated
zero-representation list, bytes freed on cleanup, an explicit statement that the classifications are
single-labeller judgements, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
