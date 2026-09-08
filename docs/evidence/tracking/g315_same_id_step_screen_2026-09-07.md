# G315 -- same-id step SCREEN (2026-09-07)
VERDICT: PREMISE HOLDS, SCREEN COMPLETE, NOTHING CHANGED -- and the screen's own answer is that TWO MODEL RATERS CANNOT AGREE ON THESE PANELS (14/30, 0.4667), so NO SWAP RATE EXISTS HERE for any game and none may be quoted; what the numbers do carry is that large same-id steps concentrate on large frame gaps in all three games, while a small one-stride residual survives that control.
Prereg sealed and committed ALONE before the first metric, the first frame and the first label: `g315_prereg_2026-09-07.md`, seal SHA-256 `277466cac9d20e86ba79e1565ade4b8b404a0abecf46a17f37c84acd44a1121a` (LF-normalized bytes above its `## SEAL` line), commit `3549ed0a8`.
GAMES, by the sealed RULE (min / median / max `p95_disp_norm` of the 13 completed rows of the committed `g309_multigame_census_2026-09-07.csv`), not by inspection. Pod inputs, READ-ONLY (A9): `data/tracking/<game>/tracking_data.csv` and `data/footage_corpus/{ncaa_basketball__ncaa_basketball_sRtHQbywiTE.mp4 243,724,897 B 1280x720 | ncaa_basketball__ncaa_basketball_mRkuGgeECak.mp4 487,249,282 B 1920x1080 | wnba__wnba_05.mp4 136,656,761 B 1280x720}`; `nb_frames` 28,904 / 28,905 / 28,815 equals each game's G309 `decoded_frames` exactly.
PREMISE (step 0, binding): HOLDS -- p95 >= 0.30 on all three -- Reproduced from the fetched tables under the G309 conventions, and it is a BIT-EXACT re-measurement, not a quotation: `p95_disp_norm`, `n_steps` and `rows` all match G309 at delta 0.0e+00 on all three games.
| game | n_steps | p50 | p75 | p95 | max | share > 0.30 | candidates |
|---|---|---|---|---|---|---|---|
| ncaa_basketball_mRkuGgeECak | 5,570 | 0.0279 | 0.1371 | 0.7317 | 2.9800 | 0.1533 | 854 |
| ncaa_basketball_sRtHQbywiTE | 1,643 | 0.0112 | 0.0426 | 0.4348 | 1.4582 | 0.0682 | 112 |
| wnba_05 | 4,726 | 0.0279 | 0.0995 | 0.8594 | 5.8089 | 0.1346 | 636 |
DENOMINATORS: every share above is over that game's own `n_steps` (5,570 / 1,643 / 4,726); a step is two consecutive same-`player_id` observations ordered by `frame`, no interpolation across a gap; displacement is Euclidean image px over `source_height` (1,080 / 720 / 720); percentiles are NEAREST-RANK. 0 rows dropped in all three games. `stride_g` = 3 in all three. The p50/p75 columns are the headline the p95 hides: the TYPICAL step is 0.011-0.028 of frame height, so the 0.73 reading is a tail, never a central tendency.
STEP 1 -- CANDIDATES, SPLIT BY GAP (a large step over a large gap is not the same claim) -- Bins sealed before measurement: B1 `gap == 3`, B2 `3 < gap <= 15`, B3 `gap > 15`. Counts are the sealed metric; the bin denominators and within-bin shares are POST-HOC and additive, labelled as such, and move nothing.
| game | B1 cand / n | B2 cand / n | B3 cand / n |
|---|---|---|---|
| ncaa_basketball_mRkuGgeECak | 516 / 4,792 = 0.1077 | 199 / 551 = 0.3612 | 139 / 227 = 0.6123 |
| ncaa_basketball_sRtHQbywiTE | 16 / 1,358 = 0.0118 | 12 / 142 = 0.0845 | 84 / 143 = 0.5874 |
| wnba_05 | 248 / 4,006 = 0.0619 | 89 / 330 = 0.2697 | 299 / 390 = 0.7667 |
The candidate share rises monotonically with the gap in ALL THREE games (0.01-0.11 -> 0.08-0.36 -> 0.59-0.77). That is the innocent explanation doing most of the work: most large same-id steps span a gap over which the identity was not observed at all. It does NOT dispose of B1: 516 / 16 / 248 candidates cross more than 0.30 of frame height across a SINGLE stride, 3 frames, 0.1 s at 30 fps.
POST-HOC, additive, registration-free -- the one-stride step in units of the pair's own mean bbox HEIGHT (a standing player is about one box height, so this reads as body-heights per 0.1 s): median 0.075 / 0.046 / 0.062, p95 2.270 / 0.343 / 1.227, max 14.882 / 5.885 / 10.755, and the share above 2 body-heights per stride is 0.0591 / 0.0081 / 0.0250 (n = 4,792 / 1,358 / 4,006). The median one-stride step is unremarkable; a 0.8-5.9 pct minority is not physically reachable by a player.
POST-HOC control that FAILED to explain anything, reported because it failed: bbox height above half the frame height covers 0.2187 / 0.0000 / 0.2395 of ALL steps and 0.2389 / 0.0000 / 0.2327 of CANDIDATE steps. Oversized boxes are a property of two of these three tables generally, not of the candidates, so they do not discriminate. They are filed below as their own NEW GAP.
STEP 2 -- CONTACT SHEETS: sampling rule stated BEFORE any panel was rendered -- Sealed rule (prereg section 5), NOT a top-10 slice (A3/B7): sort a game's candidates ascending by normalised step, take the 10 at nearest-rank decile MIDPOINTS, ranks `ceil((2i+1)/20 * n_cand)`, i = 0..9, evaluated in exact integer arithmetic (the float form returns 55.00000000000001 -> 56 at n = 100). Sampled ranks therefore sweep the whole candidate distribution, e.g. wnba_05 ranks 32..605 of 636, steps 0.3237 to 2.6139.
30 panels rendered HEADLESS (PIL, never `cv2.imshow`): frame A and frame B side by side, each with that frame's own box and a zoom crop beneath, `player_id` / both frame indices / gap / normalised step printed on it. Frames cut READ-ONLY on the pod with `ffmpeg 6.1.1-3ubuntu5` `select=eq(n,N)` into `/tmp/g315_<game>/`, then `scp`-ed out; nothing under `/workspace/nba-ai-system` was written and the `track_daemon` was never signalled.
STEP 3 -- TWO INDEPENDENT MODEL RATERS (not ground truth, and they did not converge) -- Rubric fixed in the sealed prereg BEFORE any panel existed; each rater saw only the rubric and the 30 full-resolution panels, neither saw the other's labels, and no disagreement was adjudicated.
| rater | model | SWAP | NOT-SWAP | UNREADABLE |
|---|---|---|---|---|
| A | Claude Opus 5 (claude-opus-5[1m]) | 17 | 6 | 7 |
| B | Claude Sonnet 5 (claude-sonnet-5) | 8 | 5 | 17 |
AGREEMENT 14/30 = 0.4667 overall; per game 6/10 mRkuGgeECak, 3/10 sRtHQbywiTE, 5/10 wnba_05. All 16 disagreements (A/B, S = SWAP, N = NOT-SWAP, U = UNREADABLE):
   mRkuGgeECak_02 U/N; mRkuGgeECak_04 U/S; mRkuGgeECak_08 S/U; mRkuGgeECak_09 S/U
   sRtHQbywiTE_02 S/U; sRtHQbywiTE_03 S/U; sRtHQbywiTE_05 S/U; sRtHQbywiTE_07 N/U
   sRtHQbywiTE_08 N/U; sRtHQbywiTE_09 N/U; sRtHQbywiTE_10 S/U; wnba05_01 S/N
   wnba05_02 S/N; wnba05_05 N/U; wnba05_06 S/U; wnba05_07 S/U
13 of the 16 are UNREADABLE against a call, i.e. the raters disagree about whether the panel is JUDGEABLE, not mostly about who is in the box. No consensus number is computed and none may be: 0.4667 agreement on a 3-label task is the result.
Where the free text DOES converge, it converges on something neither label captures: both raters independently name crowd, bench, courtside staff, a graphic, a net/rim or an off-frame sliver INSIDE a player box on 12 of 30 panels, and at least one rater does so on 18 of 30. That is a count of rater free text, not a label, and not a rate.
Q6 note: three geometric reason terms were reworded to 'border' under verifier correction; labels unchanged; current scoped text is clean.
NEW GAPS (named, not fixed; this row changes nothing) -- NEW GAP: in 2 of 3 games about 22-24 pct of ALL player observations carry a bbox taller than half the frame height, so for those rows the bbox bottom-centre is not a player's feet and every footpoint-derived quantity built on them -- this row's step included -- is measuring a box, not a person.
NEW GAP: both raters, independently and under different labels, report non-player content (crowd, bench, courtside staff, graphics, off-frame slivers) inside a player box on 12 of the 30 panels; a detector precision census is the row that would size this, and it has not been run.
NEW GAP: these panels are not reliably readable by model raters (0.4667 agreement). Whatever measures a swap rate on this corpus needs human labels, or panels that make the identity decision easier, or both; a second model rater pair is not it.
NOT VERIFIED -- No ground truth of any kind. Two model raters are two correlated readers of the same rendered panels and share the failure modes of the models that run them; 30 examples over 3 games is a screen for whether a labelling effort is worth mounting. No swap RATE is established for any game and no number here may be quoted as one.
Fix 1b (verifier correction): three rater reason cells re-worded to 'border' (labels unchanged); rank 604 -> 605; hashes refreshed.
Image space only (`coordinate_space = image_px`): no court, foot, metre, speed or registration claim is made, implied, or may be read into these numbers. The body-height normalisation is a scale-free ratio of two image quantities, not a physical speed.
Innocent causes NOT excluded for any individual candidate: a camera cut, a pan, a zoom, a re-detection after occlusion. The gap split is the only control offered and it is a control on the POPULATION, never on a single panel; rater A explicitly judged four sRtHQbywiTE panels to be a pan rather than a cut, and that judgement is unverified.
The frame-index mapping (`frame` = 0-based index into the source decoded sequence) is an INFERENCE supported only by `nb_frames` matching `decoded_frames` on all three games and `timestamp = frame / source_fps`; G198 (prefetch frame misalignment) is an open defect against it, and a systematic off-by-k would move which people are inside the drawn boxes.
All three games are `passed = false` in the daemon ledger, the three are not a sample of anything, and nothing here generalises past these files. The pod tree was mutating throughout. The other 10 G309 games, `features.csv`, `events_log.csv`, `ball_tracking.csv` and `resolver_debug.json` were not read; nothing was re-decoded to check determinism; no per-panel render was repeated (B11: the panels come from one run).
NOT MEASURED: whether a candidate corresponds to any real association error in the tracker's own state -- this row never opened the tracker, only its output table.
ARTIFACTS (SHA-256 of the worktree bytes; the prereg SEAL above is over LF-normalized bytes) -- b963a7027a96885683f19b56b846ded2e79cc7c09a8b5bdc1aa581762b06bbaa g315_prereg_2026-09-07.md
640b5d0301b64ce04f9fa1411d146b2e2bae0c35936a703ca4a99524fca36bce g315_same_id_step_screen_2026-09-07.csv (3 rows)
c4216445f79c6b72bf0bcd02164642e830cebd7a5f2dd346481160cc2ad98270 g315_same_id_step_screen_2026-09-07_examples.csv (30 rows)
59e1e06470abd6fb3dc348c59f8771a6c601a5648f25c65a17fa683514fad93a g315_rater_A_labels_2026-09-07.csv
b3b7d5976ce06f4dde212c252019b6ace063b8f5a1679af560730c653fbbddd0 g315_rater_B_labels_2026-09-07.csv
e22b3fd964d05fa1a26ab5fa87133a36c0b8684239f080b5fadbada0657395c6 g315_panel_manifest_2026-09-07.txt (SHA-256 of each of the 30 full-res panels; panels stay in the lane scratchpad)
8a68fb8a9d2a89911bfc235c066cc5e62c9697ec4f33d90d66b6d2386e9c4db5 g315_contact_sheets/g315_sheet_ncaa_basketball_mRkuGgeECak.jpg (466,259 B)
bd6b65344790d05f2a2b8770425d6e61914a6dc0cb52abfbea78a33d52c38b31 g315_contact_sheets/g315_sheet_ncaa_basketball_sRtHQbywiTE.jpg (386,604 B)
a5153527d61f20f6e932808ad2d80660bcf2fb9a5a6004fb8ee1582478a2ec20 g315_contact_sheets/g315_sheet_wnba_05.jpg (316,860 B) -- 1.14 MB for all three sheets
3ca9747fc9c205b971ec9538bffc55d8f428b3774edb766a8fbdce5f185f475f scripts/platformkit/tracking/g315_same_id_step_screen.py (215 lines)
2577d1e3af34ed487f088f66950ba572b07867696241db4b5ab21d4dd3052f28 scripts/platformkit/tracking/g315_render_panels.py (156 lines)
71cf8298d9aabd49238820440b4279143e9bf0da2c10e4e4c60c7be689d988ed tests/platformkit/test_g315_same_id_step_screen.py
TEST: `python -m pytest tests/platformkit/test_g315_same_id_step_screen.py -q` -> 4 passed (n = 1 CONSTRUCT, hand-computed step / gap-bin / candidate / decile-midpoint values). `tests/platformkit/test_loc_rail_scope.py` -> 1 passed; no allowlist entry was needed or raised (both new files are under the 300-line rail).
MUST NOT MOVE, and did not: no write to `data/registry/`, `src/`, `domains/`, `api/`, `kernel/`, `intel/`, `tracking_harness.py`, the register, or `TRACKING_GAPS_2026-09-01.md`; no threshold moved; no flag flipped; nothing deployed to the pod; no PROPOSED diff, because this row proposes no production change.
TIME SPENT: about 1 h 15 min wall clock, of which roughly 35 min was pod frame extraction (the first attempt decoded to end-of-file after the last selected frame and was replaced with a `-frames:v` early exit) and about 8 min was the two raters.

## Corrections applied at landing (2026-09-07)
CORRECTION 1 of 1 (verifier codex-sol, G315_VERIFY_2026-09-07.md line 29): line 35 above, the obsolete present/verbatim Q6 claim, was replaced verbatim with the verifier's replacement text. No other line, artifact, hash or label changed at landing.
VERIFIER NEW GAP (1 of 2): the full-resolution individual panels and the three raw source tables are absent from this worktree; verification used the committed contact sheets, the summary rows, the label files and the hashes only.
VERIFIER NEW GAP (2 of 2): scripts/platformkit/tracking/g315_render_panels.py has no importing test; its committed output is covered visually and by hashes only.
