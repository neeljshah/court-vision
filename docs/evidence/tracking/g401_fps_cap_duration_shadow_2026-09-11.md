VERDICT: PARTIAL -- policy metric MEASURED (16/34 = 47.1% of post-preference sections lost more than 5 s to the cap, so the 30 fps preference alone is NOT sufficient for this window; 5 UNKNOWN plus 1 FAILED_ATTEMPT); paired 60 fps mechanics NOT VALIDATED (29/30, not the sealed 30/30); additive proposal DONE, reviewable only, applied nowhere.

Prereg sealed alone at a37fed51b, SEAL
35133397a0d6ef07f71ebbb05b4248867acf498889056cf48e34b48bf12cd568, re-verified byte-for-byte.
Contract `VERIFIER_CONTRACT.md`. **Step 0** (full receipts in `policy_receipt.json`, `common_receipts/pod_step0.log.txt`). Daemon
pid 3177187, cwd `/workspace/deploy/nba-ai-system`, untouched; ledger 2033 rows at 14:01:07Z.
Active cap `--frames 3000` at `track_daemon.py:96` in `build_command` (`:80`), single caller
`Popen` at `:376`. The cap is in SOURCE-frame units (`unified_pipeline.py:1534-1537` divides by
the stride), so it buys 100 s at 30 fps and ~50 s at 59.94 fps; `--start-frame` default 0, never
passed; `_VRAM_FLUSH_INTERVAL = 3000` (`:1656`) untouched. Deploy sha256 track_daemon 9747d9a0,
run_clip ccd08d32, unified_pipeline c4eae385, all matched by the a11 worktree's LF bytes.
CORRECTION: the preference activated at **13:08:37Z**, not ~13:52Z (`relaunch.log` `RESTARTED
13:08:37 prefer-30fps selector (G397)`), and `feeder_pod.sh.bak_1350Z` (c887a8d8) is the
PRE-preference copy differing only at line 156. Live selector `-f
"$fmt/312/301/311/300/bv*[protocol*=m3u8][height>=720][height<=1080]"`, probe bar h264 and height
>= 720, `fmt` gated to 270 or 312.

**Policy metric, sealed window 13:08:37Z to census 14:07:17Z.** 34 completed post-preference
sections (>= 30), earliest terminal ORIGINAL attempt each, no repeats. Available span from decoded
native PTS of the retained source; cap-limited span from start 0 and the LAST PROCESSED SOURCE
FRAME in each section's own `tracking_data.csv` -- measured, not derived. Primary metric **16/34 =
47.06%** with loss > 5 s attributed to the cap; every one is 59.94 fps, losing 36.5-50.0 s against
a ~130 s source (median cap-limited span 52.97 s). All 30 fps and 23.98 fps sections lost nothing.
Attribution CAP 25, EOF 3, FAILED_ATTEMPT 1, UNKNOWN 5; the 5 UNKNOWN are sections whose sources
the quota guard pruned before retention -- PARTIAL supply, never inferred, and UNKNOWN blocks only
a zero-loss sufficiency verdict. The window's own composition is the finding: 21 of 34
post-preference sections were still 59.94 fps.

**Paired CPU-decode shadow, 30 retained 60 fps sources.** Population 89 retained native 59-61 fps
sections with >= 100 s spans over 18 games; 30 drawn by `floor(j*(N-1)/29+0.5)` over
competition/game/section/digest order, no replacement or substitution. All 62 retained sources
raw-byte verified pod to PC, 0 mismatches; fps cross-validated by two ffprobe readers plus the
decoded PTS grid. Arm A cap 3000, arm B cap `ceil(100*validated_fps)` (5995 or 6000), same PTS
stream, same start index, existing stride algorithm untouched. Arm A reaches 100 s on **0/30**
(50.000-50.086 s); arm B reaches it within one native frame interval on **29/30**, and the sealed
bar is 30/30, so this arm is NOT VALIDATED. `nba__1rZZ_7buX_Y_s5474.mp4` overshoots to 100.0885 s
(~5.3 intervals) because its timeline carries 26 duplicate PTS and 26 dropped frames: a
frame-COUNT cap cannot land a duration target exactly where frames are missing. Recorded, not
designed around. All 30 sit on the nominal PTS grid, so all 30 are `cap_basis=VALIDATED_FPS` with
duplicate and dropped counts per source in `pts.csv`. Stride DECLARED only.

**Proposal, reviewable only, applied nowhere.**
`docs/research/organization-sprint/PROPOSED_g401_fps_cap.diff` (copy in the evidence dir), sha256
dca612ca, 45 insertions / 4 deletions in ONE file `scripts/platformkit/track_daemon.py`, `git
apply --check -p1` clean against the LF deploy bytes. It adds `duration_frame_cap()` and
`cap_receipt()`, gives `build_command` an optional trailing `source` whose default reproduces the
exact legacy 3000-frame argv, moves the existing `probe_source(path)` call before the launch so
one dict feeds both cap and ledger, and adds `requested_duration_seconds` / `requested_frame_cap`
/ `cap_basis` / `legacy_frame_cap` to the ledger row. **Zero new argv flags**: all 7 sealed
fixtures parse with the UNCHANGED `run_clip.py` parser, so run_clip, unified_pipeline,
`_VRAM_FLUSH_INTERVAL`, workers, stride, models and thresholds are untouched. `reader_survey.csv`
lists 716 reader rows of the cap and count names, 3 inside the changed function; every other name
and alias is preserved.

**NOT VERIFIED.** Runtime cost of processing more than 3000 frames, which crosses
`_VRAM_FLUSH_INTERVAL = 3000`; receipt retention and output quality across that boundary;
producer-EVALUATED tick coverage under either cap; any tracking-quality effect of a longer window;
what the 5 pruned sections would have shown. Duration mechanics only, no deployment decision. Two
fresh processes reproduced every table and all 30 render digests. Q6 over 23 text artifacts incl.
`.log.txt`: 0 hits.
