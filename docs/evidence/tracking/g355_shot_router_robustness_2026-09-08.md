VERDICT: DONE -- both defects reproduced and fixed; 2/2 new + 8/8 landed tests pass; golden identity on all 6/6 sections (12/12 file checks) except 18 additive ANCHOR rows; 0 threshold moves; 0 src edits.
# G355 shot-router robustness (finisher)
Spec: docs/evidence/tracking/specs/G355_spec.md. Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md.
Prereg: docs/evidence/tracking/g355_prereg_2026-09-08.md, seal sha256
b9751ebdd75b3ebbb7de055d0b07d841d412e9dbbc2435c99c0dce23458bfb1c (unchanged).
PREMISE (from the sealed prereg record; re-confirmed by the fix behavior below):
ROUTER_BEFORE ValueError: not enough values to unpack (expected 2, got 1), at
shot_router.py:68 (pre-fix), a single-descriptor second frame. ANCHOR_BEFORE_ROWS 0:
a one-frame shot produced zero propagate_frames rows on landed G341 code.
FIX (additive only; file:line on HEAD 240ffd86a): shot_router.py:65-72
`_static_inlier_fraction` guards ndim!=2 or shape[0]<2 -> 0.0 (unobservable,
not a crash). floor_motion.py:102-107 `estimate_floor_motion` same guard ->
reason `too_few_descriptors` (dormant on real video below; only the synthetic
test exercises it). floor_motion.py:143-147 `propagate_frames`: every
shot-start position emits one ANCHOR MotionRecord instead of a silent
`continue`-skip. shot_router.py:226,234,251 `write_report`: `scored_motions`
excludes ANCHOR from n_steps/accepted/rejected so section counts are unchanged.
GOLDEN RERUN (local; all 6 source sha256 verified vs the G341 memo first;
single process, section order = prereg order): golden.csv (6 sections x 2
files, zero-padded) -- every row other_diff_rows=0, identical_flag=1.
propagation.csv anchor rows/section: nba_Hm7V4=1, nba_m7K0J=1, ec_mhi=5,
ec_qrWmO=5, euroleague=1, nbl=5 (=18 = total shot count). shots.csv: 0 diff, 0
anchors on all 6 (unaffected by the fix). Raw rerun bytes are CRLF (csv
module's RFC4180 terminator, `newline=""`, this platform) vs the landed
checkout's LF; compared LF-normalized, per this repo's own precedent (G341
memo states its SHA-256s as "LF-normalized"). Non-anchor propagation.csv rows:
3907/3907 byte-identical to landed post-normalization. Router print summary
(n_frames/cuts/trigger_n/replay/accepted/steps/longest_chain/p90/rejected)
matches the landed G341 memo on all 6 sections. Rerun CSVs (.../pod_output/)
NOT committed (content-identical to landed except CRLF + anchors); sha256 below.
HONEST LIMITATIONS: robustness/regression check only, not a WIDE-cue or
accuracy validation (G350 out of scope). `too_few_descriptors` never fires on
real footage in this corpus. Golden covers the six landed G341 sections only;
all six were locally AVAILABLE (none ABSENT), so no PARTIAL is triggered.
EYE CHECK: NONE. Say that.
NOT VERIFIED: pod code identity (rerun ran locally -- files were AVAILABLE and
RAM budget disfavored a pod round trip); raw (non-LF-normalized) `cmp` of the
CSVs (they differ only by CRLF vs LF, see above); anything beyond the stated
6x2 golden check.
Wall time: golden rerun (single process, six sections, local) not separately
stopwatched; one call, comparable to the landed G341 memo's own single-process
six-section baseline (163.4s). Tests: robustness file 11.57s (2, cold cv2
import); G341 file 3.96s (8).
SHA-256 (raw bytes; modules/tests unchanged since the codex lane's prep):
shot_router.py db2eee79..804f5dc; floor_motion.py d0129fb1..555460b;
test_g355_shot_router_robustness.py a16b21a1..a889768; test_g341_shot_router.py
8dc57969..a383f50; golden.csv 03929d14..56af69; anchor_rows.csv
5f35d8fb..6599a9; rerun shots.csv (not committed, raw CRLF) 93c1e585..76a391;
rerun propagation.csv (not committed, raw CRLF) ba65abb1..a753e3c.
2026-09-08 lander: ACCEPT (codex-sol, contract A/B/Q, no corrections, no new gaps); shot_router.py and floor_motion.py updated on master with golden identity on the six landed G341 sections (18 additive ANCHOR rows).
SCAN: `git diff 782273e24 240ffd86a -- scripts/ tests/` plus
golden.csv/anchor_rows.csv, grepped case-insensitively against the project's
do-not-claim restricted-word list and its retracted-digit list: 0 word hits,
0 digit collisions in the code diff or the new artifacts.
agent: FINISHER COMPLETE
