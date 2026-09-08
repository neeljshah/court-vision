VERDICT: PARTIAL -- shuffle control fails the >=20pp bar (n too small); the ball evidence is decorative on this corpus for this screening.

# G344 - ball evidence to shadow possession state (2026-09-08, LOCAL, FINISHER)

Interpreter: C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe. Prereg: g344_prereg_2026-09-08.md, seal 98ce3227549060791ef6e792d60a65ce4cea54ac670ef9f58d3b834a9fabf75d (verified). Minimal fix: added `_read_window()` to `ball_shadow_possession.py` (windowed CSV read) and switched `_main()` to use it -- some mirrored `tracking_data.csv` files run 12-22 MB and free RAM was ~2.2-3.4 GB; no threshold, no `ball_join.py`, no consumer touched. Module 182 -> 197 lines (cap 250).

PREMISE (codex-lane rerun, reproduced): `ball_join.py --report` on wnba_05 = 1000/907/93, dist n=904 p50=188.07 p95=545.51; wnba_02 = 1000/803/197, dist n=803 p50=1097.20 p95=1419.05. No existing ownership-state module found on master. Premise holds.

G343 `windows.csv` absent on this branch; applied the sealed prereg rule: 354 eligible NBA ids (both tables present, nonzero size, excluding wnba_05/wnba_02), sorted lexically, every 15th id at 0-indexed step (0,15,...,345) -> 24 ids. All 24 have max frame >= 659, so every window is [600,659]; none needed the final-60 fallback. WNBA tables use the same [600,659] window and their own in-file `source_height=720` column (confirmed, not assumed). NBA tables carry no `source_height` column; 720 assumed by the WNBA precedent -- NOT VERIFIED.

SYNTHETIC: 200/200 cases exact-match on state + owner_id, seed 3440908; all 5 kinds (valid/cut/missing/duplicate/motion_disagreement) present. `synthetic.csv`.

PER-WINDOW (OV=OBSERVED_VALID of 60, ABS=ABSENT of 60, own=accepted-owner count, m=motion-agreement accepted/candidate; INFERRED=AMBIGUOUS=0 in all 26):
0625:OV0,ABS60,own0,m0/0 5004:OV10,ABS50,own0,m0/0 5036:OV0,ABS60,own0,m0/0 5054:OV20,ABS40,own1,m1/2 5093:OV10,ABS50,own0,m0/1 5158:OV10,ABS50,own0,m0/3
5214:OV0,ABS60,own0,m0/0 5325:OV10,ABS50,own0,m0/0 5348:OV1,ABS59,own0,m0/0 5377:OV0,ABS60,own0,m0/0 5487:OV0,ABS60,own0,m0/0 5511:OV0,ABS60,own0,m0/0
5576:OV10,ABS50,own0,m0/0 5630:OV10,ABS50,own0,m0/0 5725:OV0,ABS60,own0,m0/0 5744:OV0,ABS60,own0,m0/0 5799:OV4,ABS56,own0,m0/0 5906:OV20,ABS40,own0,m0/0
5939:OV15,ABS45,own0,m0/0 5968:OV10,ABS50,own0,m0/0 1089:OV20,ABS40,own0,m0/0 1134:OV20,ABS40,own0,m0/0 1159:OV20,ABS40,own0,m0/0 1185:OV17,ABS43,own0,m0/0
WNBA05:OV10,ABS50,own0,m0/0 WNBA02:OV20,ABS40,own0,m0/2

POOLED (n=1560 = 26 x 60): OBSERVED_VALID=237 (15.2%), INFERRED=0, ABSENT=1323 (84.8%), AMBIGUOUS=0; owner_share=1 (0.06%); abstain_no_ball=1323, abstain_no_player_in_radius=229, abstain_motion_disagreement=7, abstain_cut=0.

SHUFFLE CONTROL (motion agreement = accepted-owner / rows that reached the motion check): unshifted 1/8=12.5%; shift -30f: 0/7=0.0% (drop 12.5pp); shift +30f: 4/13=30.8% (agreement rose, drop -18.3pp). Neither meets the sealed >=20pp-drop bar. The pooled denominator (8 of 1560 frames reach the motion check at all) is too small for a stable estimate -- honest finding: the ball evidence is decorative on this corpus, and the control is also underpowered.

PREFIX INVARIANCE: 3 real windows (0022400625, 0022500004, 0022500036), frames 600-629 vs the first 30 rows of 600-659, byte-identical CSV text: True/True/True. Synthetic construct check (0-3 vs first 4 rows of 0-6) also holds (`test_prefix_invariance_cut_stop_and_stale_age`).

STALE/CROSS-CUT: 0/1560 OBSERVED_VALID rows carry nonzero age_frames (structurally: OBSERVED_VALID requires the current frame's own detected ball, so age=0 whenever OBSERVED_VALID -- age>30 can never yield it). 0/1560 rows carry abstention_reason=cut: G341 has not landed on this branch (spec file only, no artifact), so cuts=UNKNOWN=empty set for all 26 windows; cut-blocking is exercised only on the synthetic "cut" case.

EYE CHECK: NONE.

NOT VERIFIED:
- Nearest in-radius player is not necessarily the ball handler; a wrong or airborne ball can look smooth.
- Ball and player points are image pixels (bottom-centre bbox / ball_x2d,y2d), never floor positions.
- source_height=720 for the 24 NBA tables is assumed (no such column in their header), matched to the WNBA tables' own explicit column; a wrong assumption rescales the 60px radius.
- 24 windows + 2 WNBA tables are a screening; the motion-agreement control (n=8 unshifted) is underpowered regardless of the verdict.
- G314/G320 evidence dirs hold no committed raw WNBA CSVs (images only); wnba_05/wnba_02 came solely from the local `data/tracking/` mirror -- see `file_manifest.csv`.
- No consumer is wired; dynamic/runtime readers of this module are not traced.

FILES: 52 inputs (24 NBA ids x 2 tables + 2 WNBA ids x 2 tables), 292,988,135 B pooled; every path, byte size and SHA-256 in `file_manifest.csv`. The fix commit touches only `scripts/platformkit/tracking/ball_shadow_possession.py`.

SHA-256 (LF-normalized bytes): states.csv=191584de376b613fe88d57434d92c8d7604599e1bcbc696b2637bae1acf5b9bf (79863 B); synthetic.csv=d905c8326ef6d74ee859a78b5d45d21794e9b48346c379e35d753a0756ed597c (10320 B); file_manifest.csv=cb6c8c7aee74e68f3bd6877a944ea9af3e7ce3f045d8803ebef506ab685cc713 (5310 B).

WALL TIME: 2026-09-08 13:58-14:06 CDT (~8 min).
