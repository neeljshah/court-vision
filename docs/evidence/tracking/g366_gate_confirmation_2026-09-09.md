VERDICT: PARTIAL -- evaluated-tick ratio median 0.153195 falls outside [0.90,1.10]; stationary_track_share A0 rejection 0.203390 (12/59) exceeds 0.05 on unplanted fresh sections; v2 candidate detection fails A1_FROZEN 0.000000 and A2_ID_MERGE 0.542373 (bar 0.80) though its own A0 rejection 0.050847 (3/59) is close to the 0.05 bar. Sampling bar clears (59 sections/14 games) and zero_step_share / distinct_position_ratio both confirm (M1 0.000000).

# G366 gate confirmation on fresh games -- memo

Row G366 | worktree `/workspace/wt/a12` (pod, branch track-a12) | Spec `docs/evidence/tracking/specs/G366_spec.md` VERSION 2026-09-09. Prereg `g366_gate_confirmation_2026-09-09/g366_prereg_2026-09-09.md`, `SEAL sha256 af4285e560598ba0b8512c3521d78604ef6b01b80949532bf8c4d0de84578e4a` over its first 299 lines, re-verified this session (`test_the_preregistration_seal_covers_every_line_above_it` passes). Finisher: claude-sonnet.

## Premise (re-read, not a new measurement)
Re-read `docs/evidence/tracking/g359_held_position_vs_threshold_2026-09-09/decision.csv` on MASTER (`8fd4407d`, G359 landed `73c6cbc3` since prereg seal): `zero_step_share` clear_M0 0.705882/clear_M1 1.000000 PRODUCTION_SCHEMA_ARTIFACT; `distinct_position_ratio` clear_M0 0.735294/clear_M1 1.000000 PRODUCTION_SCHEMA_ARTIFACT; `median_step_distance` clear_M0 0.941176/clear_M1 0.088235 THRESHOLD_MISCALIBRATED (v2 candidate 76.995468); `stationary_track_share` clear_M0 0.911765/clear_M1 0.911765 UNDECIDED. `held_share.csv` 35 lines (34 rows), `arms.csv` 4897 lines, both on master, pre-collapse denominators retained. 3 of 4 carry a class: PREMISE HOLDS.

## G359 module copy
`g359_held_position.py` copy in a12 is byte-identical to the landed master file (both sha256 `433efcef718dcdf4ca92deea66f4feac576131093d3904f0161eaed4b2b36ece`); a no-op against current master, per the prereg post-seal amendment.

## Fresh set (census then sample; `fresh_sections.csv`)
Ledger snapshot `/workspace/g366_ledger_snapshot.jsonl` sha256 `a3bb94db3cf76d79c574839847220eff1b3a6b5a28152954a2eac797ffe71604` (933 lines, 2026-09-09T20:32:12Z). Census over the snapshot: 923 ledger sections, 59 ELIGIBLE across 14 games, disjoint from the G358 34 sealed sections and their 17 games by construction (ladder steps 4-5). Sample: eligible n=59, `n > 40` so `k = floor(59/30) = 1` (same result as a CONSTRUCT at this n) -- all 59 selected, 14 games. Bar (>=30 sections/>=10 games) CLEARS. `frame_size_source` = `estimated` on all 59 (vs `absent` on every G358 sealed section).

## Per-gate A0 confirmation (fresh set, n_paired=59 every gate; M1 bar <=0.05, M0 beside it, Wilson 95pct)
    zero_step_share          M0 0.406780 [0.291,0.534]   M1 0.000000 [0.000,0.061]   CONFIRMED
    distinct_position_ratio  M0 0.372881 [0.261,0.500]   M1 0.000000 [0.000,0.061]   CONFIRMED
    stationary_track_share   M0 0.203390 [0.120,0.323]   M1 0.203390 [0.120,0.323]   NOT CONFIRMED (over 0.05)
    median_step_distance v1  M0 0.000000 [0.000,0.061]   M1 0.949153 [0.861,0.983]   NOT CONFIRMED (unchanged class)

## Evaluated-tick audit (`ticks.csv`, n=59, all with a ledger record, bar median in [0.90,1.10])
median 0.153195, p10 0.023059, p90 0.553901, min 0.010761, max 0.726364 -- NOT IN BAND. `m1_player_frames / ledger_evaluated_frames` runs far below 1 on every fresh section; the fresh pool evaluated_frames field does not track the post-collapse player-tick count the way it did over the G359 34-section basis.

## Stationary plant (`plants.csv`, 10 sections, `even_pick`, both modes)
M0 detected 10/10 = 1.000000 [0.722,1.000] Wilson; M1 detected 10/10 = 1.000000 [0.722,1.000]. Both clear the >=0.80 bar. Combined with the unplanted-A0 miss above, stationary_track_share is NOT CONFIRMED overall -- detection alone does not satisfy the prereg two-part bar.

## v2 candidate (`v2.csv`, fresh-only, additive, direction max, threshold 76.995468)
A0 M1 rejection: v1 0.949153 (56/59, unchanged) vs v2 0.050847 (3/59) [Wilson 0.017,0.139] -- 0.000847 over the 0.05 bar. Detection with v2: A1_FROZEN 0.000000 [0.000,0.061] (FAILS, bar 0.80), A2_ID_MERGE 0.542373 [0.417,0.663] (FAILS, bar 0.80), A5_BALL_SHIFT 0.050847 [0.017,0.139] (REPORTED, inherits the G358 13/34=0.382 LIMIT, not re-barred). v2 does not clear either bar.

## Reach (`reach.csv`, A0, n=59 both modes)
The 4 confirm gates: 1.000000 reachable, n_paired 59. NOT_APPLICABLE both modes: `coordinate_contract` and `oob` (cause `court_space_required`), `g325_wholly_off_frame` (cause `frame_size_absent` -- `estimated` does not satisfy the gate `{decoded,sidecar}` requirement, so this stays unreachable exactly as under the G358 fully-absent set). MEASURED_NO_BAR/UNIDENTIFIABLE (reached_n 0): `coverage_attempted_frames`, `attempted_frames`, `jump_max`, `jump_p95` (same causes as G358). `any_gate` M1: 1/59 pass, 58/59 reject; detection_any_gate A1_FROZEN/A2_ID_MERGE both 1.000000, A5_BALL_SHIFT 0.983051 -- the full gate set still catches what median_step_distance_v2 alone misses.

## Sign convention
A0 higher share = worse (false rejection, bar <=0.05); A1/A2/A5/plant higher share = better (detection, bar >=0.80); delta = M1 minus M0; tick-ratio bar is a two-sided band on the median. Per prereg section 0.

## Tests (pod python3, worktree a12)
`test_g366_gate_confirmation.py` 6 passed; `test_loc_rail_scope.py` 1 passed.

## Wall time
Snapshot (20:32:12Z) to `summary.json` (20:45:07Z): about 13 minutes (809s), dominated by the arms step (about 3m40s over 59 sections times 4 arms times 2 modes) and the ticks step (about 4m, re-adapts and collapses all 59 sections).

## SHA-256 (A11)
`g366_fresh.py`=`ce2ed36050a71964030658c8fbda294dfae2728ce761024cd7f60e8611a4a527`; `g366_confirm.py`=`b20d6c9adba84de2ed93cfe09bf99847c4b2f7d755eec7e638ed6b43821ac1a4`; `test_g366_gate_confirmation.py`=`e8d331b1d32ca59fbaea281483a6cac6cd7f9cc16beafbc4d430428d8abce434`; `g366_prereg_2026-09-09.md`=`5adb1d1193bd50bf32606e8bc498fe9006e7dd45e243bba10e61cb54d610a702`; `g359_held_position.py`=`433efcef718dcdf4ca92deea66f4feac576131093d3904f0161eaed4b2b36ece`; `fresh_sections.csv`=`c3bc22c67bd39700640d510cd2a1b11d5f8331d7816a5b0a925aa757d618c0d2`; `gates_fresh.csv`=`ef263a1f2437948befcd9151670d1a2fda1ee0d22cd3d8cb208325c5567d98fe`; `v2.csv`=`e3b664521478a66efa5c2c47a2c0a20f23dff50d770c00ea08713c8befc41418`; `plants.csv`=`f9fde9e38b339e5751d83c31bba8ce64a35b709632c934efd90c8fe49e431707`; `ticks.csv`=`cea4c897158f668179111d142a771b1b8c8685fd5b5d252f9e8cbf6337bd5327`; `reach.csv`=`efe8fcab3972708d57aee720759efb9311506a58769de73c753cd7485558cf64`; `summary.json`=`acbe79635d23428de23acef077db3f82484cccd6f53af3ff61078f4670c117a8`; ledger snapshot=`a3bb94db3cf76d79c574839847220eff1b3a6b5a28152954a2eac797ffe71604`.

Vocabulary follows contract Q6; automated scan required.
SCAN (`/workspace/g366_scan.py`, patterns assembled from single characters at run time, word-boundary; run over this memo, the prereg, the seven CSV/JSON artifacts, the two modules and the test).
SCAN OUTPUT (verbatim counts, exit 0): 28 hits total, all in the artifacts named below; this memo has 0 hits.
NAMED EXCLUSION 1 (18 hits): shell sigil in a command block -- g366_prereg_2026-09-09.md lines 240,241,247,248,250,252,253,254,256,257,259,260,263,265,266,268,271,272 (opaque identifiers exempt under the Q6 NOTE; prereg never rewritten after its seal).
NAMED EXCLUSION 2 (10 hits): digit substring inside a measured statistic -- gates_fresh.csv lines 2318,2390,2426,3016,3023,6655,6763; ticks.csv line 45; v2.csv lines 371,377 (none is the retracted figure itself; each is a full-precision measured value that happens to contain the substring).

## NOT VERIFIED (extends the builder list, never shortens it)
Whether the evaluated-tick ratio would land in band on a different fresh snapshot; the corpus rotates and this row measures one. Whether stationary_track_share would confirm with a wider fresh sample; 59 sections gave a cleaner signal than G359 34 but still misses the bar. Whether a v2 threshold between v1 (8.408436) and the candidate (76.995468) would clear both the A0 and detection bars; this row scores only the one preregistered candidate. Any court geometry: `frame_size_source` is `estimated`, never `decoded`/`sidecar`, on all 59 sections. A5_BALL_SHIFT as a real ball-shift detector (inherited G358 LIMIT). Any claim beyond this fresh snapshot. No monetary or wagering interpretation of any figure in this row.

## Landing note
One RESULTS_LEDGER.md row is appended in this commit; the register row is left for the verifier (spec EVIDENCE clause; this finisher does not touch the register).
