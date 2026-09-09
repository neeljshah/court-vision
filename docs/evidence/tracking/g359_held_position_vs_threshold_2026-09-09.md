VERDICT: DONE -- 4 gates classified on the sealed 34 sections/17 games (2 PRODUCTION_SCHEMA_ARTIFACT, 1 THRESHOLD_MISCALIBRATED, 1 UNDECIDED); A1_FROZEN and A2_ID_MERGE detection = 1.0000 in BOTH arms, clearing the >=0.80 bar; check-default 792/792 cells match the landed G358 output; 0 thresholds moved, 0 flags flipped, 0 src edits.

# G359 held-position artifact vs threshold miscalibration

Row G359 | worktree /workspace/wt/a10 (pod) | Spec docs/evidence/tracking/specs/G359_spec.md VERSION 2026-09-08 | Prereg g359_prereg_2026-09-09.md sealed at 6d102e5d (seal a6681140ac7e1e07231323f7ba757b751d99730c5cbd96a4d02447351cad4200). Finisher: claude-sonnet. Eye check: NONE. Ledger snapshot: /workspace/g359_ledger_snapshot.jsonl, 912 rows, taken 2026-09-09 19:42:01 UTC.

## Premise (held_share.csv)
Sealed input = the LANDED fix-1c list (34 sections, 17 games; 33 POST_EPOCH + 1 G346_LIVE), per corrected input Q8, not the 6-section text in the spec. n=34, held share min/median/max = 0.332797 / 0.750378 / 0.985276, sections >= 0.20 = 34/34 (no section below the bar). PREMISE HOLDS; row proceeds to section 3.

## Two arms, gates unchanged (arms.csv; any_gate, FULL, n=34 reached a status in both modes)
    A0 false rejection    M0 0.3824 [0.2390,0.5496]  M1 0.9118 [0.7704,0.9695]
    A1_FROZEN detection   M0 1.0000 [0.8985,1.0000]  M1 1.0000 [0.8985,1.0000]  bar>=0.80 CLEARS
    A2_ID_MERGE detection M0 1.0000 [0.8985,1.0000]  M1 1.0000 [0.8985,1.0000]  bar>=0.80 CLEARS
    A5_BALL_SHIFT         M0 0.3824 [0.2390,0.5496]  M1 0.9118 [0.7704,0.9695]  reported, not barred
95 pct Wilson, two-sided (n=sections). A5_BALL_SHIFT is IDENTICAL to A0 in both modes: the G357/G358 ball-coverage LIMIT persists and A0/M1's rise is the median_step_distance spike below, not a ball-plant effect.

## Decision per gate (decision.csv; n_paired=34 for all four; unchanged sealed threshold in both modes)
    gate                     clear_M0  clear_M1  class
    zero_step_share          0.7059    1.0000    PRODUCTION_SCHEMA_ARTIFACT
    distinct_position_ratio  0.7353    1.0000    PRODUCTION_SCHEMA_ARTIFACT
    stationary_track_share   0.9118    0.9118    UNDECIDED (M0 already clears >=0.90; not a live rejecter on this set)
    median_step_distance     0.9412    0.0882    THRESHOLD_MISCALIBRATED
A0 per-gate rejection M0/M1 (95 pct Wilson): zero 0.2941 [0.1683,0.4617]/0 [0,0.1015]; distinct 0.2647 [0.1460,0.4312]/0 [0,0.1015]; stationary 0.0882 [0.0305,0.2296]/same; median-step 0.0588 [0.0163,0.1909]/0.9118 [0.7704,0.9695].
Candidate v2 (preregistered, unscored): median_step_distance_v2 = 76.995468 (quantile 0.95 of the M1 distribution). 0 thresholds moved; 0 flags flipped; 0 src edits; every adapter row scorable=False.

## Byte-identical default-output check
check-default: 792/792 M0 cells reproduce the landed g358_full_section_gate_execution_v2_2026-09-08/gates.csv (FULL, 4 constructible arms) exactly; mismatches=0.

## Analytic predictions (prereg section 11) vs measured
stationary_track_share invariant under the collapse: CONFIRMED, 0/34 sections differ between M0 and M1 (checked per section, not only at the median). zero_step_share and distinct_position_ratio move away from the sealed threshold: CONFIRMED (M1 clear share 1.0000 vs M0 0.7059 / 0.7353). median_step_distance moves toward its threshold with a HIGHER M1 rejection share: CONFIRMED (clear share 0.9412 -> 0.0882).

## Sign conventions
held_share = share of comparable consecutive same-track row pairs that are byte-identical; higher = more held (the defect under test). rejection_share = rejected_n / evaluated_n, PASS+REJECT only; higher is WORSE on A0, BETTER (detection) on A1/A2/A5. A displayed delta is M1 minus M0.

## Tests (pod python3, each file alone)
test_g359_held_position.py: 9 passed. test_loc_rail_scope.py: 1 passed. (test_g358_gate_execution.py / test_g353_image_space_gates.py not re-run this row: imported, unedited modules, already verified under their own G358/G353 rows.)

## Wall time and SHA-256 (A11)
Wall time of the 34-section two-arm loop (arms step): 56.9s (log birth 19:42:39.639 UTC, last write 19:43:36.518 UTC).
SHA-256 g359_held_position.py 433efcef718dcdf4ca92deea66f4feac576131093d3904f0161eaed4b2b36ece
SHA-256 g358_gate_execution.py 92f4bfba01d283f20418bd41b0c43ed23364b55e203ccfed1276b270d03852e5
SHA-256 production_schema_adapter.py dabc1070de4c531299fe1f59fdfae8c8436bff5179039ffa6bb227aafe73be02
SHA-256 image_space_gates.py f90651c00290ac2afc7726e213d60fa8d11ae68ccc4ac612e4806e739c3c7a9a
SHA-256 liveness_metrics.py 50839e08fbb06112f77a0cc03e80b248dc54cbe1ee53e164fca244256ba150f0
SHA-256 ledger_snapshot.jsonl (912 rows) 00e70922a360c6dcd9242c6df01ea122a1cac31506b23e5bb24f469148b8534b
SHA-256 held_share.csv 7f56f09588160ba6719d87beca6bacee2b304c0f21af425405f92edac13f9818
SHA-256 arms.csv ff76039470109595e1a3602ecfeb0809605e4121c9a92a45070eff70065e71ce
SHA-256 decision.csv 6a9c3e07827520049caaf37cd63ee3b918ace38aa74dc424efe904b35bc1f2f3

## Vocabulary scan (contract Q6)
python3 /workspace/g358_scan.py over this memo, held_share.csv, arms.csv, decision.csv, g359_held_position.py, test_g359_held_position.py.
NAMED EXCLUSION 1, never silent: the sealed prereg scans separately and returns 8 mechanical hits, all the shell-variable sigil in its section 12 command block (lines 301, 304, 309, 311, 315, 319, 324, 325) -- command-line identifiers quoted verbatim, exempt under the Q6 NOTE; the prereg is not rewritten after its seal.
NAMED EXCLUSION 2, never silent: arms.csv lines 3893 and 3929 (section ncaaw-lFZWLVzvCEs_s2232, gates A0/M0 and A1_FROZEN/M0, coverage_attempted_frames) carry the real, unrelated measurement 0.1191919191919192; its leading digits coincidentally match the retracted 0.119 figure as a bare substring, it is not that figure, and the measured cell is never edited to hide the coincidence.
SCAN OUTPUT (all 6 files, full run): 11 hits total -- 8 in the sealed prereg (Named Exclusion 1), 2 in arms.csv (Named Exclusion 2), 1 in this memo on the Named Exclusion 2 sentence itself (quoting the excluded figure verbatim to name it); held_share.csv, decision.csv, g359_held_position.py, test_g359_held_position.py: 0 hits each.

## NOT VERIFIED
Any court geometry (frame_size_source absent on these sections; g325_wholly_off_frame, oob, jump_max, jump_p95, coordinate_contract, coverage_attempted_frames reach no bar in either mode, exactly as in G358). A5_BALL_SHIFT as a real ball-shift detector: its figure is identical to A0's false-rejection baseline in both modes, so it may be entirely artifact-driven rather than plant-driven (a LIMIT, not a pass). Any claim beyond these 34 sections / 17 games, a single snapshot of a rotating corpus. The candidate v2 threshold for median_step_distance (preregistered here, unscored). No monetary or wagering interpretation of any figure in this row.
