# G352 FIX 1b render index (moved verbatim from the evidence memo in fix 1c, no numbers changed)

This file holds the fix-1b render methodology and the per-render court-visibility
description that used to live inline in the evidence memo under "FIX 1b RENDERS".
It was moved here ONLY to bring the memo under its 60-line cap (contract B2: no
scored number, gate, or claim changed by this move). The memo keeps a short
pointer + summary in its own "FIX 1b RENDERS" section.

## Section header (verbatim, memo line 47 as of fix 1b)

## FIX 1b RENDERS (2026-09-09, corrects B7 head-slice evidence)

## Methodology (verbatim, memo line 48 as of fix 1b)

The 12 renders in `renders/` were all taken at the prereg's sealed index `evaluation_indices[(2*arm_index+1) % len]`, which resolves to rank 2, 4 or 6 of the 60-frame sealed decision set for ARM_A/ARM_B/ROUTE, then snaps forward to the nearest frame that arm actually scored -- landing at actual rank 5-11 (the first ~18 pct of every set) on all 12, a B7 head slice, never an even sample. `renders_fix1b/` replaces the SAMPLE only: `renders/` and every scored number are untouched (B2). Rule: 3 renders per section per arm at the ranks nearest 20, 40 and 60 of 60, chosen ONLY from eval_index values already present in `perframe.csv` for that section and arm (no new frame was fit; `renders_fix1b/index.csv` carries section, arm, sealed_rank, actual_rank, frame, fraction_of_set for all 18). `g352_run.score_frame` -- the lane's own renderer, unedited -- was re-invoked on each already-decided frame; `reason` came back `valid` at all 18, consistent with the archived row's own `reason` at that same eval_index.

## Sources (verbatim, memo line 49 as of fix 1b)

S1 (nba__Hm7V4jOxlUI_s3633) and S2 (nba__m7K0J4wzDn4_s2070): both YouTube ids report "Video unavailable" as of 2026-09-09 (checked with and without a format filter); their sources cannot be recovered, so S1 and S2 have no `renders_fix1b` and are NOT VERIFIED (below). S3 (id mhi_fuXUPRE) and S4 (id YqB41CtbFqA) were re-fetched via the pod's yt-dlp recipe (format 270, section 90-260s; `renders_fix1b/sources.csv` carries the new sha256, format, fps, dims). ALIGNMENT CAVEAT: yt-dlp/ffmpeg rebase the trimmed clip's own timeline to PTS 0 (ffprobe reports `start_time=0.000000` on both fresh files), so the same id and offset do NOT guarantee identical bytes, and frame N in the fresh copy is not guaranteed to be the same real-world instant as frame N in the archived copy -- only that the SAME sealed integer `eval_index` (a pure function of the sealed `frame_count`) was requested from both.

## What the 18 renders show (verbatim, memo line 50 as of fix 1b)

What the 18 renders show: rank ~20-21 (frame 1306/1373 S3, 1092/1148 S4) and rank ~40-41 (2646/2713 S3, 2212/2268 S4) stay on the same no-court content as the original eye-check (S3: interview backdrop; S4: title card at rank20-21, player-roster graphic card at rank40-41). Rank ~51-58, the LAST third of each set, is where S3 and S4 diverge from their "no court" billing: `S3_G352A_rank57.jpg` (frame 3785) and `S3_ROUTE_rank58.jpg` (frame 3852) show a full court floor with a team mascot/kids and a player lineup, crowd behind; `S4_G352A_rank57.jpg` and `S4_ROUTE_rank58.jpg` (frame 3164/3220) show a sideline interview with the arena and crowd visible behind the presenters. `S3_G352B_rank51.jpg` (frame 3383) is a dark, underlit arena shot (ambiguous) and `S4_G352B_rank51.jpg` (frame 2828) is a close-up of a player's jersey with no floor visible (ambiguous) -- both NOT VERIFIED for court-visibility, below. `renders_fix1b/{S3,S4}_contact_sheet.jpg` tile all 9 renders per section for an at-a-glance look.
