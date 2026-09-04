GAP G213 | sport all | worktree a7 | log g213_footage_visual_census
**MEASUREMENT ONLY. Change NO production code.** `src/` is HUMAN-GATED: READ only. Build in
`scripts/platformkit/tracking/`.

**S1 MACHINE: the corpus is on the POD. This row is deliberately LIGHT and the limits are BINDING.**
G203 is still measuring decode byte identity there.
  - **ALLOWED: single-frame seeks** (`ffmpeg -ss <t> -i <file> -frames:v 1`), at most **5 frames per
    clip**. A seek decodes one GOP, not the file.
  - **FORBIDDEN: any full decode, `ffprobe -count_frames`, `run_clip.py`, model inference, GPU work,
    and touching the daemon, keeper, bridge or watchdog.** Delete NOTHING.
  - If your approach would breach any of those, **STOP and say so** rather than proceeding.

**S3 DEPENDENCY. G209 did the metadata half and correctly REFUSED to do this half.** It established:
11 of 11 clips probed at the time; **variable-frame-rate 0/11, portrait/non-16:9 0/11, audio-free
0/11**; **sub-720p IS represented** (one 640x360 clip, correcting the orchestrator's assumption). It
then declined to assign either a positive or a zero count to **amateur/high-school capture style,
fixed single-camera, heavy scoreboard/graphics overlay, non-standard playing surfaces, and poor
lighting**, on the ground that stream metadata cannot establish any of them -- noting explicitly that
NCAA competition is not proof of amateur capture. **That refusal was right, and those are exactly the
categories that decide arbitrary-footage robustness.** The corpus has since grown; **enumerate it
yourself** and name the count you actually probed.

THE QUESTION, and it is the programme's current goal in one line: **what does our footage actually
look like, and what kinds of footage do we have NO examples of?** The target is tracking any game from
any video per sport. Nearly every measurement to date (G189, G190, G193, G195, G198, G203) ran on ONE
clip, `wnba__wnba_01.mp4`.

METHOD:
  1. Enumerate every complete corpus clip. Name the ELIGIBLE DENOMINATOR and every exclusion.
  2. Per clip, extract **5 frames evenly spaced across the duration** (not the first 5 seconds --
     openings are titles and studio shots and would misrepresent the clip).
  3. **Look at them and classify each clip, one line per clip, against a FIXED rubric you state up
     front.** At minimum: camera style (broadcast pan/zoom vs fixed wide vs handheld); production tier
     (professional broadcast vs amateur/home capture); scoreboard or graphics overlay (none / light /
     heavy, and whether it occludes the playing surface); playing-surface visibility (what fraction of
     the surface is typically in frame); surface appearance (standard vs unusual colour or markings);
     and lighting (well-lit arena vs dim gym).
  4. **Then answer the gap question directly: which rubric categories have ZERO examples in this
     corpus?** Be concrete and unflattering. **"Every clip is professional broadcast with a moving
     camera; we have zero amateur, zero fixed-camera and zero dim-gym footage" is the expected shape
     of the answer and is a FULL SUCCESS.**
  5. Commit the extracted frames as evidence so a later reader can check your classification. Keep
     them small (downscale if needed) and say what you did.

**THIS IS A HUMAN-JUDGEMENT ROW AND YOU MUST SAY SO.** Your classifications are eye labels with no
second labeller, so **report them as single-labeller judgements and do NOT attach a confidence you
cannot support.** Where a clip is ambiguous, say ambiguous rather than forcing a category. **Do not
infer capture style from the sport or league name** -- that is the exact error G209 called out.

**DO NOT** propose a fix, tune anything, recommend a model change, or draw a tracking conclusion. This
row characterises footage; it measures no tracking outcome.

ACCEPTANCE RULE:
  metric        = per-clip classification against the stated rubric; the count of clips in each
                  category; an explicit list of rubric categories with ZERO representation
  before        = the corpus has never been visually characterised; metadata (G209) established
                  resolution/fps/codec but provably cannot establish camera style, tier, overlay,
                  surface or lighting
  bar           = NO pass bar. The deliverable is an honest characterisation and a blunt gap list.
                  **A finding that the corpus is monolithic is the most valuable outcome**, because it
                  says robustness claims cannot rest on it.
  n             = every complete corpus clip (CONSTRUCT, exhaustive) x 5 evenly spaced frames
  eye check     = the classification IS the eye check; commit the frames
  must not move = every threshold, bar and verdict, the coordinate contract, `src/` (READ ONLY), the
                  pod daemon, keeper, bridge and watchdog, the corpus (delete NOTHING, download
                  NOTHING)
EVIDENCE: docs/evidence/tracking/g213_footage_visual_census_2026-09-03.md with the rubric stated up
front, the per-clip table, the committed frames, the zero-representation list, an explicit statement
that these are single-labeller eye judgements, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
