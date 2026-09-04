# G278: Stratified follow-up to the G275 painted-court census

## Verdict

**ACCEPT (measurement only): category (a) occurred in 51 / 61 = 0.836 new within-span frames, compared with 118 / 180 = 0.656 clip-wide in G275.** The within-span 95% Wilson interval is [0.724, 0.908]. The pooled two-proportion comparison gives pooled p = 0.701245, SE = 0.067811, z = 2.661959, and nominal two-sided p = 0.007769, with no correction for the many comparisons in this programme.

**With 51 / 61 new within-span frames versus 118 / 180 clip-wide and nominal two-sided p = 0.0078, the studied span is unusually court-bearing, so the chain was measured on friendlier footage than the clip-wide average.**

This does not move G275's counts or verdict. Category (a) remains necessary, not sufficient, for a usable map.

## Where each part ran, inputs, and disk guard

Part A ran in POD scratch `/workspace/wt/a5`, because the full-resolution corpus source is read-only there. It used `~/bin/pod_run a5 --ship scripts/platformkit/tracking/g278_census_followup.py --fetch docs/evidence/tracking/g278_census_stratified_followup_artifact/part_a.tar -- <guarded command>`. Part B ran locally in `C:\Users\neelj\nba-track-a5`: it re-judged G275's committed frames, with no decode and no POD use.

Part A opened `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4`, 2,931,985,407 bytes, SHA-256 `f361ad7a32ccc6d98ae8e98eee0b090f5e121f9425182e24a31c282ca226c678`, 1920x1080, 30 fps, 174,430 ffprobe frames. The POD harness verified its hash and metadata before extraction. The POD-exercised route was `scripts/platformkit/tracking/g278_census_followup.py`, SHA-256 `9886588c062147c17320996864b52b8bb8ba30b508609425ee25ab793cf37864`.

Part B opened the exact selected JPEGs under `docs/evidence/tracking/g275_map_eligible_footage_census_artifact/blind_frames/`: 40 images, 6,984,430 bytes total, each 1920x1080. It copied them with `shutil.copyfile`, with no decode, crop, or pixel alteration. Their full source-ID and SHA-256 mapping is in [the Part B manifest](g278_census_stratified_followup_artifact/part_b/blind_manifest.json).

The required guard inside the Part A command recorded `du -sm /workspace = 38,507 MB`, then passed `dd if=/dev/zero of=/workspace/wt/a5/.g278_fsync_probe.bin bs=1M count=1 conv=fsync`; the 1,048,576-byte probe was removed before extraction. `pod_run` separately recorded 38,506 MB and removed its 8,388,608-byte quota probe. The 15,933,440-byte fetched transport tar was verified, unpacked, and removed both locally and from POD scratch: it freed 15,933,440 bytes at each location; POD scratch freed 25,370,624 bytes total including both probes. No corpus source, `baseball__npb_05.mp4.part`, or `football__football_m8UWuQoflJo.mp4.part` was deleted.

Before dispatch, the running peer Python-worktree set was `{ /workspace/wt/a17 }`, one distinct lane, below the two-worktree hold. No process was interrupted.

## Unchanged categories and sealed blind protocol

Both parts used exactly G275's categories, unchanged:

| Category | Verdict |
|---|---|
| (a) | two or more distinct painted court lines visible AND at least one intersection of painted lines visible |
| (b) | painted court surface visible but not that |
| (c) | no painted court surface at all |
| (d) | cannot judge |

The full blind orders and verdicts are committed in [Part A manifest](g278_census_stratified_followup_artifact/part_a/blind_manifest.json), [Part A labels](g278_census_stratified_followup_artifact/part_a/blind_labels.csv), [Part B manifest](g278_census_stratified_followup_artifact/part_b/blind_manifest.json), and [Part B labels](g278_census_stratified_followup_artifact/part_b/blind_labels.csv). These blind materials and verdicts were committed in `4d4f85d80bc06f941eb0aa8bdcd12bbaf8c73b01` before source/category unblinding. The subsequent reproducible join is [summary.json](g278_census_stratified_followup_artifact/summary.json).

## Part A: new uniform within-span sample

The inclusive span 19599-23399 has 3,801 frames. A centred 60-frame plan would have overlapped G275 frame 20834, so the first non-overlapping at-least-60 centred design is 61 frames: stride `3801 / 61 = 62.311475` frames, with adjacent gaps of 62 or 63. It does not reuse G275's four span frames 19865, 20834, 21803, or 22772. Each new frame came from its own `ffmpeg -ss <frame/30> -i VIDEO -frames:v 1` seek, never a one-pass decode.

Chronological new indices:

```text
19630,19692,19754,19817,19879,19941,20004,20066,20128,20190,20253,20315,20377,20440,20502,20564,20627,20689,20751,20814,20876,20938,21001,21063,21125,21187,21250,21312,21374,21437,21499,21561,21624,21686,21748,21811,21873,21935,21997,22060,22122,22184,22247,22309,22371,22434,22496,22558,22621,22683,22745,22808,22870,22932,22994,23057,23119,23181,23244,23306,23368
```

Blind order (`blind_id:source_frame`):

```text
0:22060,1:21935,2:20128,3:21686,4:21873,5:23119,6:21001,7:22434,8:19817,9:20190,10:21437,11:22745,12:21250,13:21624,14:19941,15:22309,16:20502,17:20315,18:21561,19:22621,20:21125,21:22371,22:23306,23:22558,24:20066,25:21748,26:23057,27:22932,28:20938,29:23368,30:21312,31:20751,32:23181,33:21811,34:19879,35:22247,36:22184,37:19630,38:20253,39:22808,40:20876,41:21187,42:21499,43:22496,44:22994,45:20814,46:21374,47:20004,48:20564,49:20440,50:22870,51:20689,52:21997,53:21063,54:20377,55:23244,56:19754,57:22683,58:19692,59:20627,60:22122
```

Counts in the named denominator of 61 are (a) 51, (b) 2, (c) 8, and (d) 0. The interval is descriptive uncertainty for this small within-span sample; it is not an exact population fraction. The test includes all 61 Part A frames and all 180 G275 frames, with `(d)` counted rather than excluded.

## Part B: local stratified re-judge

Composition was 20 random first-pass (a), **all 11 first-pass (b)**, and 9 random first-pass (c) frames: 40 / 40 total, with no first-pass (d). Fresh blind order (`rejudge_id:g275_blind_id`):

```text
0:19,1:37,2:68,3:22,4:131,5:93,6:34,7:134,8:3,9:101,10:170,11:175,12:174,13:156,14:61,15:57,16:73,17:128,18:81,19:141,20:100,21:98,22:106,23:31,24:119,25:55,26:120,27:49,28:103,29:77,30:142,31:85,32:32,33:15,34:50,35:75,36:136,37:79,38:111,39:1
```

Rows are first-pass category and columns are fresh re-judge category.

| First pass / re-judge | a | b | c | d |
|---|---:|---:|---:|---:|
| a | 20 | 0 | 0 | 0 |
| b | 0 | 11 | 0 | 0 |
| c | 0 | 0 | 9 | 0 |
| d | 0 | 0 | 0 | 0 |

The threshold-setting cells are first-pass a -> re-judge b = **0 / 20** and first-pass b -> re-judge a = **0 / 11**. All eleven first-pass (b) frames repeated as (b); agreement is 40 / 40, including 31 / 31 at the (a)/(b) strata.

**This measures repeatability, not correctness.** It is one labeller using the same criteria. Low agreement would falsify the precision of 0.656, because a call that cannot be repeated cannot be right. High agreement does not validate it, because both passes can be consistently wrong in the same way; the G275 figure is not confirmed here.

The zero observed a->b and b->a transition rates leave the repeatability-adjusted point at `118 / 180 = 0.656`. The 20 / 20 a->a sample has a 95% Wilson lower repeatability rate of 0.838875; scaling only as a repeatability screen gives a 95% measured floor `(118 * 0.838875) / 180 = 0.550`. All 11 b frames re-judged as b, leaving only the un-rejudged d as a repeatability-screened upward possibility: `(118 + 1) / 180 = 0.661`. The resulting **[0.550, 0.661] is a repeatability-only bound, not a correctness interval or corrected prevalence estimate.**

## Evidence, limits, and contract self-check

The artifact contains 116 files / 24,776,502 bytes: Part A has 69 files / 15,873,735 bytes and Part B 46 files / 8,901,657 bytes, plus [summary.json](g278_census_stratified_followup_artifact/summary.json). The boards cover all blind frames, not a head slice.

This memo follows `docs/evidence/tracking/VERIFIER_CONTRACT.md`. A2: summary recomputes counts, test, and confusion from committed manifests and labels. A3/B7: Part A retains all 61 uniform within-span frames and Part B was freshly randomized. A4: all Part A indices and Part B/G275 IDs are unique. A5/B2-B6: the landing is additive evidence plus a measurement harness; no production schema, reader, lifecycle, deployment, source module, or moved module changed. A7: each linked path exists. A9/A11 name the inputs and POD route. B1 keeps every `(d)` in the named denominator. B8 has no fitted geometry. B9 names denominators. B10 changes no bar. A12: this new 256-line file grows no existing allowlisted file; `tests/platformkit/test_loc_rail_scope.py` passes. Q does not apply.

**NOT VERIFIED:** calibration success, correct maps, residuals, or usable homographies for any (a) frame; category correctness or a second labeller; other clips, broadcasts, arenas, or sports; a shot count or population prevalence; and any causal explanation for the within-span difference. This is one clip, one broadcast, one arena, one labeller. Uniform frames weight long views by runtime, not shots. This blind classification is a coarse categorical judgement, not the sub-pixel geometric measurement G257 bounded at 20 px. G274 produced 0.569 px RMS on a frame with no court in it, so visible painted geometry never establishes that a map would fit or be correct.
