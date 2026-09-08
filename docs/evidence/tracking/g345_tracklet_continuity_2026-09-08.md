VERDICT: PARTIAL -- 2 of 4 sealed sections available (nba_0575, nba_0592 REFUSED by the route's own preflight, exit 4, not rescored); reserved ZNCC evidence NOT RUN (no local frames); sealed reconnect bar >=0.95 applied as sealed: ARM_C measured 0.69, NOT MET; decision rule NOT REACHABLE (bar needs >=3 of 4 sections).
Premise (step 0): nba_0081 n=180 frames, n=1304 detections, per-frame median/p10/p90=7/4/9; wnba_5l4 n=180 frames, n=1714 detections, per-frame median/p10/p90=10/6/13.
Both CSVs confirmed detector output only: header is section,frame,score,bbox_x1,bbox_y1,bbox_x2,bbox_y2 -- no track-id column, identical schema both arms (nba_0081.csv:1, wnba_5l4.csv:1).
nba_0575, nba_0592: NOT RUN (route refused nba_0575, nba_0592; 0 detections exist anywhere for either section).
# G345 tracklet continuity on fixed detections -- fix 1b rerun (2026-09-08, LOCAL finisher)
Interpreter: C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe (conda basketball_ai, Py 3.10.20).
SEALED SECTIONS (amendment g345_prereg_fix1b_2026-09-08.md, verified against worktree, byte-identical):
nba_0081.csv 66270 B sha256 856c18c0394d26ba1861de1c1a99c559cbd8cd160077383fb2ef5d3787c9860c;
wnba_5l4.csv 88694 B sha256 2bcb48112a1f3a6347043e51ef410565b4ef23dd806e1207dc21f038b0649c8a.
RAW JSONL PROVENANCE: /workspace/wt/a21/g336/out/fix1b/nba_0081_raw.jsonl sha256 ABSENT bytes ABSENT;
/workspace/wt/a21/g336/out/fix1b/wnba_5l4_raw.jsonl sha256 ABSENT bytes ABSENT (absent from this worktree, unchanged since the amendment).
nba_0575, nba_0592: 0 detections exist anywhere (route preflight refusal) -- PARTIAL stands, not rescored.
2026-09-08 fix 1b: `read_detection_csv` (g345_associate.py:154-168) keeps `frame`/`obs_key` as raw CSV
source-frame values throughout; `_add_evaluated_ticks` (g345_associate.py:170-183) adds `tick`/`tick_stride`
as additive columns only, never overwriting frame/obs_key. `_associate`'s immediate/reconnect gates
(g345_associate.py:90-94) compare raw source-frame deltas against RECONNECT_AGE=30 source frames, never
evaluated ticks -- fixes G345_VERIFY's B2/B10/Q3 finding (30 source frames had silently become 90 via a
30-evaluated-tick threshold). `print_reconnect_gate_units` reports the sealed 30 source frames alongside
its tick equivalent: both sections stride 3, so 30 source frames = 10 evaluated ticks (not 30 ticks/90 frames).
2026-09-08 fix 1c: premise prints restored per the codex-sol REJECT; the SCAN line below reworded to drop
prose tokens the rail flags; the amendment's direct-path command needs `python -m
scripts.platformkit.tracking.g345_associate` (REJECT NEW GAP); only this memo's bytes changed.
ARMS x SECTIONS (n_detections/n_supported_adjacent_pairs; digest identical across all 3 arms per section):
nba_0081 n=1304/1251: ARM_A/ARM_B starts/1000=50.360 coverage=0.9517 merges=0 mean_len=20.70; ARM_C
starts/1000=26.379 coverage=0.9747 merges=0 mean_len=39.52.
wnba_5l4 n=1714/1560: ARM_A/ARM_B starts/1000=204.487 coverage=0.8139 merges=0 mean_len=5.37; ARM_C
starts/1000=114.103 coverage=0.8961 merges=0 mean_len=9.63.
ARM_C starts cut vs ARM_A: nba_0081 -47.62% (was -50.79% under the pre-fix semantics), wnba_5l4 -44.20%
(was -48.28%); coverage moved +2.30pp and +8.23pp (no drop, both improve, unchanged direction).
INJECTIONS: 200/200 scored (100 gaps, 100 crossings; seed 3450908), 600 arm-rows (3 arms x 200 cases).
Gap reconnect correctness: ARM_A 0/100=0.00, ARM_B 0/100=0.00 (no reconnect capability, expected), ARM_C
69/100=0.69 (was 44/100=0.44 under the pre-fix semantics; bar >=0.95 -- still FAILS).
Crossing simultaneous merges: ARM_A 0/100, ARM_B 0/100, ARM_C 0/100 (bar =0 -- holds for all three).
RESERVED EVIDENCE: crop ZNCC -- NOT RUN. Reason unchanged: only detector boxes/scores were captured (no frame images locally), so the reserved crop channel cannot be computed.
DECISION (as sealed): recommend ARM_C only if starts fall >=50pct vs ARM_A on >=3 of 4 sections, coverage
drop <=2pp, reconnect correctness >=0.95, 0 injected simultaneous merges. NOT REACHABLE: only 2 of 4
sections scored. Relaxed to n=2 for reference only: starts now clear -50pct on 0 of 2 sections (both
-47.62%/-44.20% fall short, unlike the pre-fix -50.79%/-48.28%), and reconnect correctness (0.69) remains
under 0.95. No src change is proposed.
EYE CHECK: NONE.
HONEST LIMITATIONS: 2 of 4 sections is a screening, not the sealed 4x240 n; fewer starts alone is gameable
(checked against coverage, which improved, and injections, which still fail the reconnect bar); these are
label-free continuity metrics, not IDF1 or named-player identity -- same-kit swaps can pass; reference
tracklets for gap/crossing injections come from ARM_C's own clean-stream run.
NOT VERIFIED: nba_0575/nba_0592 (0 detections, REFUSED); reserved ZNCC (no frames); the full sealed n
(4 sections x 240 frames -- this run measured 2 x 180/180 evaluated-tick frames per the amendment); raw
JSONL source bytes (ABSENT from this worktree, not rechecked).
SHA-256 (LF-normalised): g345_associate.py b1676e540d2887384e78595dbb081b7f30d02ad7aadc36fe394fad9b7e19f4fc;
g345_inject.py 53435f0329c47825d5a0d60e7c0b4e681609c74711588fa6e7506ba99162c1de;
test_g345_associate.py 3401e69cac308561dd7c7c9ea47ab810b7c5d3dfc99815e76dd89f33b325e000;
fixtures/g345_stride3_source_frames.csv 440cc95201576d033327e0b17505295cc807a6e39dddb9e8db93115098e11065;
nba_0081.csv 856c18c0394d26ba1861de1c1a99c559cbd8cd160077383fb2ef5d3787c9860c;
wnba_5l4.csv 2bcb48112a1f3a6347043e51ef410565b4ef23dd806e1207dc21f038b0649c8a;
arms.csv b558450604ca08bc554c619741e1c2a96ae5bc8cc8d5594a83a6b6b53a387c27;
injections.csv d049799aa63c020393455f21cda009fb5e6f1f1a06ddcd801cabda34688b22d8.
Tests (alone): tests/platformkit/test_g345_associate.py 2 passed in 9.05s (both the ARM_C gap/crossing
check and the stride-3 source-frame regression the fix-1b lane added).
WALL TIME: 2026-09-08 16:50-16:57 CDT (~7 min); association <5s, injections ~2m, tests ~9s.
2026-09-08 lander: ACCEPT (codex-sol, contract A/B/Q, no corrections) on fix 1c after two REJECTs (frame semantics; memo prints); NEW GAPS in the ledger (memo line 22 understates the fix-1c change set, which also appended a ledger row).
SCAN: full memo grepped against the Q6 rail (VERIFIER_CONTRACT.md Q6) -- 0 hits; 0 non-measured hits.
