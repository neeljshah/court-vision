# Tracking evidence durability audit -- 2026-09-02

Read-only sweep of every row of `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md` and
every memo under `docs/evidence/tracking/*.md`, run against verifier-contract clause A7
(a memo naming an evidence path that no longer exists is NOT VALIDATED).
Nothing in the register, any memo, or any code was modified. This file is the only write.

## Method (so every number below can be re-derived)

1. Every pipe-table data row in the register was parsed; the 4th column is the evidence cell.
   An evidence cell reading `same` was expanded to the preceding row's cell.
2. Path-like tokens were pulled from that cell (extensions md json jsonl csv py txt png jpg
   mp4 pt log, trailing-slash directories, and absolute /tmp /workspace /root paths).
3. Each cited memo was opened and the same extraction run over its BODY. That is the artifact list.
4. Every path was resolved against the local repo: as given, under the repo root, under
   docs/evidence/tracking/, then by basename against an index of 157,912 repo paths
   (.git, node_modules, venvs and caches excluded).
5. Verdicts. BROKEN = a cited memo is absent, OR a repo-relative artifact resolves to nothing
   locally, OR the row cites no checkable evidence file at all. AT_RISK = memo present and no
   hard-missing artifact, but at least one cited path is pod-only: /tmp, /workspace, or a
   data/footage_corpus broadcast clip (that directory is gitignored and holds 4 files locally
   against the 61-clip pod corpus). SAFE = everything cited resolves locally.

Three tokens are excluded from the BROKEN test by name, because their absence IS the recorded
finding rather than a durability failure: `train_59.pt` (a third-party TVCalib weight discussed
in a licence review, never our artifact), `data/models/synthcal_tennis_wave7.pt` and
`data/models/synthcal_tennis.pt` (the G06 memo states outright that no checkpoint exists).

## Counts -- denominator is 73 register rows

| verdict | rows | of total |
|---|---|---|
| SAFE | 30 | 30/73 |
| AT_RISK | 28 | 28/73 |
| BROKEN | 15 | 15/73 |

- 30 of 73 rows (41.1 pct) have every piece of cited evidence present on this machine.
- 28 of 73 rows (38.4 pct) rest wholly or partly on pod-only paths that a pod reallocation destroys.
- 15 of 73 rows (20.5 pct) would fail A7 today.

## Per-row table -- denominator is 73 rows

`memo exists` is yes when every memo the row names exists. `art cited` counts artifact paths
found in those memo bodies plus the row's own direct file citations; `art present` is how many
of those resolve locally.

| gap | cited memo(s) | memo exists | art cited | art present | risk | why |
|---|---|---|---|---|---|---|
| G44B | `g44b_ball_spatial_gate_2026-09-02.md` | yes | 11 | 11 | **SAFE** | all cited evidence resolves locally |
| G01 | `corpus_mislabel_2026-09-01.md` | yes | 10 | 8 | **AT_RISK** | 2 cited path(s) are pod-only /tmp or /workspace, absent locally |
| G02 | `basketball_imagepx_relabel_2026-09-01.md` | yes | 12 | 8 | **AT_RISK** | 4 cited path(s) are pod-only /tmp or /workspace, absent locally |
| G03 | `basketball_imagepx_relabel_2026-09-01.md` | yes | 12 | 8 | **AT_RISK** | 4 cited path(s) are pod-only /tmp or /workspace, absent locally |
| G04 | `basketball_imagepx_features_2026-09-02.md` | yes | 13 | 7 | **AT_RISK** | 6 cited path(s) are pod-only /tmp or /workspace, absent locally |
| G05 | `tennis_camera_lock_honest_measurement_2026-09-01.md` | yes | 1 | 0 | **AT_RISK** | 1 cited path(s) are pod-only /tmp or /workspace, absent locally |
| G06 | `synthcal_w7_verdict_2026-09-01.md` | yes | 17 | 8 | **AT_RISK** | 7 cited path(s) are pod-only /tmp or /workspace, absent locally |
| G07 | `soccer_s1_blind_verdict_2026-09-01.md` | yes | 4 | 4 | **SAFE** | all cited evidence resolves locally |
| G08 | `soccer_stream_packet_2026-09-02.md` | yes | 3 | 3 | **SAFE** | all cited evidence resolves locally |
| G09 | `G09_calibration_licence_research_2026-09-02.md` | yes | 1 | 0 | **SAFE** | resolves except 1 path whose absence IS the recorded finding (train_59.pt) |
| G10 | `baseball_footage_acq_2026-09-01.md` | yes | 7 | 6 | **AT_RISK** | 1 cited path(s) are pod-only /tmp or /workspace, absent locally |
| G11 | `baseball_footage_acq_2026-09-01.md`, `baseball_night_pitchview_2026-09-01.md` | NO (1/2) | 8 | 6 | **BROKEN** | cited memo missing: baseball_night_pitchview_2026-09-01.md |
| G12 | `baseball_footage_acq2_2026-09-02.md` | yes | 10 | 8 | **AT_RISK** | 2 cited path(s) are pod-only /tmp or /workspace, absent locally |
| G13 | `football_fieldview_2026-09-01.md` | yes | 8 | 8 | **SAFE** | all cited evidence resolves locally |
| G14 | `pod_deploy_2026-09-01.md` | yes | 9 | 3 | **AT_RISK** | 6 cited path(s) are pod-only /tmp or /workspace, absent locally |
| G15 | (none cited) | n/a | 0 | 0 | **BROKEN** | row cites no checkable evidence file at all |
| G17 | `soccer_s1_blind_verdict_n100_2026-09-01.md`, `soccer_role_filter_2026-09-01.md` | yes | 9 | 9 | **SAFE** | all cited evidence resolves locally |
| G18 | `tennis_sequential_plan_2026-09-01.md` | yes | 2 | 2 | **SAFE** | all cited evidence resolves locally |
| G19 | `basketball_producer_fix_2026-09-01.md` | yes | 13 | 5 | **AT_RISK** | 8 cited path(s) are pod-only /tmp or /workspace, absent locally |
| G20 | `pod_deploy_2026-09-01.md` | yes | 9 | 3 | **AT_RISK** | 6 cited path(s) are pod-only /tmp or /workspace, absent locally |
| G21 | (none cited) | n/a | 0 | 0 | **BROKEN** | row cites no checkable evidence file at all |
| G22 | `soccer_detector_determinism_2026-09-01.md` | yes | 5 | 5 | **SAFE** | all cited evidence resolves locally |
| G23 | (none cited) | n/a | 0 | 0 | **BROKEN** | row cites no checkable evidence file at all |
| G26 | `tennis_sequential_plan_2026-09-01.md` | yes | 1 | 1 | **SAFE** | all cited evidence resolves locally |
| G32 | `baseball_night_pitchview_2026-09-01.md` | NO (0/1) | 1 | 0 | **BROKEN** | cited memo missing: baseball_night_pitchview_2026-09-01.md |
| G16 | (none cited) | n/a | 0 | 0 | **BROKEN** | row cites no checkable evidence file at all |
| G24 | (none cited) | n/a | 1 | 1 | **SAFE** | all cited evidence resolves locally |
| G25 | (none cited) | n/a | 1 | 0 | **AT_RISK** | 1 cited path(s) are pod-only /tmp or /workspace, absent locally |
| G27 | `gapfinder_2026-09-02/corpus_resolution.md` | yes | 4 | 4 | **SAFE** | all cited evidence resolves locally |
| G28 | `gapfinder_2026-09-02/highres_copies_never_tracked.md` | yes | 3 | 3 | **SAFE** | all cited evidence resolves locally |
| G29 | `gapfinder_2026-09-02/ball_rows_absent.md` | yes | 3 | 3 | **SAFE** | all cited evidence resolves locally |
| G30 | `gapfinder_2026-09-02/corpus_byte_duplicate.md` | yes | 4 | 2 | **AT_RISK** | 2 cited path(s) are pod-only /tmp or /workspace, absent locally |
| G31 | `docs/evidence/tracking/tennis_pseudolabels_2026-09-02.md`, `tennis_pseudolabels_2026-09-02.md` | yes | 2 | 2 | **SAFE** | all cited evidence resolves locally |
| G33 | `baseball_scale_validation_2026-09-01.md` | yes | 6 | 6 | **SAFE** | all cited evidence resolves locally |
| G34 | `tennis_camera_lock_honest_measurement_2026-09-01.md` | yes | 1 | 0 | **AT_RISK** | 1 cited path(s) are pod-only /tmp or /workspace, absent locally |
| G35 | `RESULTS_LEDGER.md` | yes | 12 | 5 | **BROKEN** | 2 cited artifact(s) missing locally (non-fragile), e.g. harness_verdict.json; tracking_capability.json |
| G36 | `baseball_footage_acq2_2026-09-02.md` | yes | 10 | 8 | **AT_RISK** | 2 cited path(s) are pod-only /tmp or /workspace, absent locally |
| G37 | `corpus_sibling_variants_2026-09-04.md` | yes | 9 | 2 | **AT_RISK** | 7 cited path(s) are pod-only /tmp or /workspace, absent locally |
| G38 | `daemon_endtoend_verdict_census_2026-09-02.md` | yes | 1 | 0 | **AT_RISK** | 1 cited path(s) are pod-only /tmp or /workspace, absent locally |
| G39 | `g38_tennis_jump_diagnosis_2026-09-02.md` | yes | 0 | 0 | **SAFE** | all cited evidence resolves locally -- WARNING: memo names no artifact path at all |
| G40 | `g34_view_share_and_denominator_2026-09-02.md` | yes | 3 | 3 | **SAFE** | all cited evidence resolves locally |
| G41 | `RESULTS_LEDGER.md` | yes | 14 | 7 | **BROKEN** | 2 cited artifact(s) missing locally (non-fragile), e.g. harness_verdict.json; tracking_capability.json |
| G42 | `RESULTS_LEDGER.md` | yes | 12 | 5 | **BROKEN** | 2 cited artifact(s) missing locally (non-fragile), e.g. harness_verdict.json; tracking_capability.json |
| G43 | (none cited) | n/a | 0 | 0 | **BROKEN** | row cites no checkable evidence file at all |
| G44 | `g39_ball_projection_diagnosis_2026-09-02.md` | yes | 5 | 4 | **AT_RISK** | 1 cited path(s) are pod-only /tmp or /workspace, absent locally |
| G45 | `g39_ball_projection_diagnosis_2026-09-02.md` | yes | 4 | 3 | **AT_RISK** | 1 cited path(s) are pod-only /tmp or /workspace, absent locally |
| G46 | `g39_ball_projection_diagnosis_2026-09-02.md` | yes | 4 | 3 | **AT_RISK** | 1 cited path(s) are pod-only /tmp or /workspace, absent locally |
| G57 | `g46_court_scale_premise_2026-09-02.md` | yes | 2 | 2 | **SAFE** | all cited evidence resolves locally |
| G58 | `g46_court_scale_premise_2026-09-02.md` | yes | 2 | 2 | **SAFE** | all cited evidence resolves locally |
| G59 | (none cited) | n/a | 2 | 2 | **SAFE** | all cited evidence resolves locally |
| G60 | `g57_tennis_solver_generalization_2026-09-02.md` | yes | 5 | 4 | **AT_RISK** | 1 cited path(s) are pod-only /tmp or /workspace, absent locally |
| G61 | `g61_unversioned_pod_code_2026-09-02.md` | yes | 3 | 3 | **SAFE** | all cited evidence resolves locally |
| G62 | `g52_tennis_reproducibility_2026-09-02.md` | yes | 1 | 1 | **SAFE** | all cited evidence resolves locally |
| G63 | `FOOTAGE_CORPUS_INVENTORY.md` | yes | 67 | 5 | **AT_RISK** | 62 cited path(s) are pod-only /tmp or /workspace, absent locally |
| G64 | `g33b_baseball_scale_bins_2026-09-02.md` | yes | 5 | 2 | **AT_RISK** | 3 cited path(s) are pod-only /tmp or /workspace, absent locally |
| G65 | `g44b_ball_spatial_gate_2026-09-02.md` | yes | 8 | 8 | **SAFE** | all cited evidence resolves locally |
| G66 | `g66_player_candidate_labels_2026-09-02.md` | yes | 7 | 7 | **SAFE** | all cited evidence resolves locally |
| G67 | `CALIBRATION_STRATEGY_2026-09-02.md` | yes | 0 | 0 | **SAFE** | all cited evidence resolves locally -- WARNING: memo names no artifact path at all |
| G68 | `CALIBRATION_STRATEGY_2026-09-02.md` | yes | 0 | 0 | **SAFE** | all cited evidence resolves locally -- WARNING: memo names no artifact path at all |
| G69 | `CALIBRATION_STRATEGY_2026-09-02.md` | yes | 0 | 0 | **SAFE** | all cited evidence resolves locally -- WARNING: memo names no artifact path at all |
| G70 | `g66_player_candidate_labels_2026-09-02.md` | yes | 7 | 7 | **SAFE** | all cited evidence resolves locally |
| G47 | `g47_contract_rejection_census_2026-09-02.md` | yes | 6 | 0 | **AT_RISK** | 6 cited path(s) are pod-only /tmp or /workspace, absent locally |
| G48 | `g48_sampling_interval_2026-09-02.md`, `g35_gapfinder_2026-09-02.md` | yes | 27 | 17 | **BROKEN** | 1 cited artifact(s) missing locally (non-fragile), e.g. footage_cycle_ledger.jsonl |
| G49 | `g35_gapfinder_2026-09-02.md`, `soccer_stream_packet_2026-09-02.md` | yes | 26 | 16 | **BROKEN** | 1 cited artifact(s) missing locally (non-fragile), e.g. footage_cycle_ledger.jsonl |
| G50 | `g35_gapfinder_2026-09-02.md`, `g50b_null_degenerate_metrics_2026-09-02.md` | yes | 24 | 14 | **BROKEN** | 1 cited artifact(s) missing locally (non-fragile), e.g. footage_cycle_ledger.jsonl |
| G51 | `g35_gapfinder_2026-09-02.md` | yes | 23 | 13 | **BROKEN** | 1 cited artifact(s) missing locally (non-fragile), e.g. footage_cycle_ledger.jsonl |
| G52 | `g52_tennis_reproducibility_2026-09-02.md` | yes | 2 | 2 | **SAFE** | all cited evidence resolves locally |
| G33B | `g33b_baseball_scale_bins_2026-09-02.md` | yes | 5 | 2 | **AT_RISK** | 3 cited path(s) are pod-only /tmp or /workspace, absent locally |
| G53 | `g53_baseball_provenance_2026-09-02.md` | yes | 2 | 2 | **SAFE** | all cited evidence resolves locally |
| G54 | `TRACKING_PROGRAM_STATE_2026-09-02.md`, `RESULTS_LEDGER.md` | yes | 19 | 7 | **BROKEN** | 2 cited artifact(s) missing locally (non-fragile), e.g. harness_verdict.json; tracking_capability.json |
| G55 | `g42_tennis_collapse_cause_2026-09-02.md` | yes | 9 | 2 | **AT_RISK** | 7 cited path(s) are pod-only /tmp or /workspace, absent locally |
| G56 | `g42_tennis_collapse_cause_2026-09-02.md` | yes | 9 | 2 | **AT_RISK** | 7 cited path(s) are pod-only /tmp or /workspace, absent locally |
| G33B attempt 2 | `g33b_baseball_scale_bins_2026-09-02.md` | yes | 5 | 2 | **AT_RISK** | 3 cited path(s) are pod-only /tmp or /workspace, absent locally |

## BROKEN -- the rows that would fail A7 today (15 of 73)

### B1. Cited memo does not exist (2 of 73 rows)

- **G11** -- cited memo missing: baseball_night_pitchview_2026-09-01.md
  Register status text: CLOSED AT LIMIT (corrected 2026-09-03: the row said OPEN while RESULTS_LEDGER row "2026-09-02 baseball G11 ... v3 geometry-only ... REJECT; G11 closed at limit"
- **G32** -- cited memo missing: baseball_night_pitchview_2026-09-01.md
  Register status text: OPEN (LOW priority until day corpus is large)

### B2. Row cites no evidence file at all (5 of 73 rows)

These name a memory slug, a bare commit sha, or another gap in prose. There is no artifact to
open, so they cannot pass a durability check by any route.

- **G15** -- evidence cell reads: `done_means_verdict memory`
- **G21** -- evidence cell reads: `code review of 1c5f1e6b7`
- **G23** -- evidence cell reads: `G09 research`
- **G16** -- evidence cell reads: `product_runtime_contract memory`
- **G43** -- evidence cell reads: `g39/g44 memos`

### B3. Cited memo exists but names an artifact that resolves to nothing (8 of 73 rows)

- **G35** -- missing: `harness_verdict.json`, `tracking_capability.json`
- **G41** -- missing: `harness_verdict.json`, `tracking_capability.json`
- **G42** -- missing: `harness_verdict.json`, `tracking_capability.json`
- **G48** -- missing: `footage_cycle_ledger.jsonl`
- **G49** -- missing: `footage_cycle_ledger.jsonl`
- **G50** -- missing: `footage_cycle_ledger.jsonl`
- **G51** -- missing: `footage_cycle_ledger.jsonl`
- **G54** -- missing: `harness_verdict.json`, `tracking_capability.json`

All of B3 traces to three generic filenames used as if they were paths.
`harness_verdict.json` and `tracking_capability.json` are named in `RESULTS_LEDGER.md`,
`daemon_done_verdict_2026-09-02.md` and `ball_telemetry_flag_2026-09-02.md` in the form
`data/tracking/<game>/harness_verdict.json` -- a file CLASS with a placeholder segment, not a
resolvable artifact. Locally `data/tracking/` holds 418 directories and NOT ONE contains either
file (`find data -name harness_verdict.json` returns zero hits; same for tracking_capability.json).
`footage_cycle_ledger.jsonl` is named in `g35_gapfinder_2026-09-02.md` as living under
`data/tracking/`; it exists nowhere in the repo. Under A7 a reader cannot open any of the three.

## AT_RISK -- pod-only evidence (28 of 73 rows)

| gap | fragile paths cited | example |
|---|---|---|
| G01 | 2 | `/tmp/footage_census` |
| G02 | 4 | `/tmp/t3_bb_harness_2026-09-01.log` |
| G03 | 4 | `/tmp/t3_bb_harness_2026-09-01.log` |
| G04 | 6 | `/tmp/t3b_reemit/` |
| G05 | 1 | `/tmp/tennis-camera-lock-master` |
| G06 | 7 | `/tmp/synthcal_wave7_refine.py` |
| G10 | 1 | `/workspace/nba-ai-system/data/footage_bridge/` |
| G12 | 2 | `/workspace/nba-ai-system/data/footage_bridge/` |
| G14 | 6 | `/workspace/keep_track_daemo` |
| G19 | 8 | `/workspace/track_daemon.pid` |
| G20 | 6 | `/workspace/keep_track_daemo` |
| G25 | 1 | `/tmp/t3b_reemit/` |
| G30 | 2 | `data/footage_corpus/football__football_wHZt1eY3A9s_1080p.mp4` |
| G34 | 1 | `/tmp/tennis-camera-lock-master` |
| G36 | 2 | `/workspace/nba-ai-system/data/footage_bridge/` |
| G37 | 7 | `football__football_wHZt1eY3A9s.mp4` |
| G38 | 1 | `/workspace/track_daemon.log` |
| G44 | 1 | `/workspace/nba-ai-system/data/tracking/` |
| G45 | 1 | `/workspace/nba-ai-system/data/tracking/` |
| G46 | 1 | `/workspace/nba-ai-system/data/tracking/` |
| G60 | 1 | `/workspace/nba-ai-system/data/footage_corpus/` |
| G63 | 62 | `/workspace/nba-ai-system/data/footage_corpus/` |
| G64 | 3 | `/workspace/nba-ai-system/data/footage_corpus/` |
| G47 | 6 | `/workspace/nba-ai-system/data/tracking_reports/` |
| G33B | 3 | `/workspace/nba-ai-system/data/footage_corpus/` |
| G55 | 7 | `/workspace/nba-ai-system/data/tracking/` |
| G56 | 7 | `/workspace/nba-ai-system/data/tracking/` |
| G33B attempt 2 | 3 | `/workspace/nba-ai-system/data/footage_corpus/` |

Most-depended-on fragile paths, by count of rows (AT_RISK plus BROKEN, denominator 43 rows):

- `/workspace/track_daemon.log` -- 8 rows
- `/tmp/t3b_reemit/` -- 7 rows
- `/workspace/nba-ai-system/data/footage_corpus/` -- 7 rows
- `/workspace/track_daemon.pid` -- 6 rows
- `wnba__wnba_01.mp4` -- 6 rows
- `wnba__wnba_01_1080p.mp4` -- 6 rows
- `/workspace/nba-ai-system/data/tracking/` -- 6 rows
- `/workspace/nba-ai-system/yolov8n.pt` -- 6 rows
- `/tmp/t3b_reemit` -- 5 rows
- `/workspace/nba-ai-system/data/footage_bridge/` -- 4 rows
- `tennis__tennis_nyYk2nPZAwY.mp4` -- 4 rows
- `mlb__mlb_2iosUkpL0Bc.mp4` -- 4 rows
- `mlb__mlb_ARtRmUHC7dw.mp4` -- 4 rows
- `/tmp/g42_retrack` -- 4 rows
- `/workspace/nba-ai-system/data/tracking/track_daemon_ledger.jsonl` -- 4 rows

## Memo-level sweep -- every memo under docs/evidence/tracking/*.md

Denominator: 89 memo files.

- 41 of 89 are cited by at least one register row; 48 of 89 are cited by NO row.
- Across all 89 memos, 546 artifact paths are named; 273 resolve locally, 273 do not.
- 52 of 89 memos name at least one /tmp or /workspace path.
- 8 of 89 memos name no artifact path at all, so they carry a claim with nothing to open.

Memos with the most unresolvable citations (missing / cited):

- `FOOTAGE_CORPUS_INVENTORY.md` -- 62/66 missing
- `EVIDENCE_DURABILITY_AUDIT_2026-09-02.md` -- 41/42 missing
- `TRACKING_GAPS_2026-09-01.md` -- 13/28 missing
- `baseball_cut_detector_2026-09-01.md` -- 13/15 missing
- `g35_gapfinder_2026-09-02.md` -- 10/23 missing
- `g44_ball_detectability_limit_2026-09-02.md` -- 9/10 missing
- `synthcal_w7_verdict_2026-09-01.md` -- 9/17 missing
- `basketball_producer_fix_2026-09-01.md` -- 8/13 missing
- `RESULTS_LEDGER.md` -- 7/12 missing
- `corpus_sibling_variants_2026-09-04.md` -- 7/8 missing
- `g42_tennis_collapse_cause_2026-09-02.md` -- 7/9 missing
- `basketball_imagepx_features_2026-09-02.md` -- 6/12 missing

Memos that exist but are cited by no register row (%d of %d). Several are the obvious evidence
for a lane whose row cites something else instead, which is its own traceability gap:

- `CODEX_SPECS_2026-09-04.md`
- `CODEX_SPEC_TEMPLATE.md`
- `EVIDENCE_DURABILITY_AUDIT_2026-09-02.md`
- `FOOTBALL_WAVE6H_OCR_REPORT.md`
- `FOOTBALL_WAVE_6D_SCALE_SOURCE.md`
- `FOOTBALL_WAVE_6F_FIELD_ROI.md`
- `FOOTBALL_WAVE_6G_NUMERAL_OCR.md`
- `HANDOFF_TRACKING_ACCOUNT2_2026-09-02.md`
- `PREREG_BASEBALL_FRAMING_2026-09-01.md`
- `TRACKING_DAY1_EXECUTION_PLAN_2026-09-04.md`
- `TRACKING_GAPS_2026-09-01.md`
- `TRACKING_LOOP_OPTIMIZATION_2026-09-02.md`
- `VERIFIER_CONTRACT.md`
- `ball_telemetry_flag_2026-09-02.md`
- `baseball_cut_detector_2026-09-01.md`
- `baseball_s4_packet_2026-09-01.md`
- `baseball_scale_failure_bins_2026-09-04.md`
- `basketball_floor_gate_2026-09-02.md`
- `confounder_findings_2026-09-01.md`
- `daemon_done_verdict_2026-09-02.md`
- `football_imagepx_snap_2026-09-01.md`
- `g34_basketball_view_share_2026-09-02.md`
- `g34_soccer_view_share_2026-09-02.md`
- `g41_cv2_shape_hardening_2026-09-02.md`
- `g44_ball_detectability_limit_2026-09-02.md`
- `g49_soccer_churn_restate_2026-09-02.md`
- `g51_pod_drift_check_2026-09-02.md`
- `g54_evidence_durability_2026-09-02.md`
- `g55_timeout_budget_2026-09-02.md`
- `g56_ledger_denominator_2026-09-02.md`
- `g60_clay_horizontals_2026-09-02.md`
- `g62_run_environment_stamp_2026-09-02.md`
- `g65_ball_label_set_2026-09-02.md`
- `harness_sweep_173_games_2026-09-01.md`
- `ingest_regate_2026-09-02.md`
- `jump_p95_gap_bridging_2026-09-01.md`
- `reingest_720p_2026-09-02.md`
- `soccer_role_classifier_v3_2026-09-04.md`
- `soccer_s4_packet_2026-09-01.md`
- `synthcal_wave7_blocked_2026-09-01.md`
- `synthcal_wave7_render_and_look_2026-09-01.md`
- `tennis_camera_lock_nyYk_720p_2026-09-01.md`
- `tennis_intersection_ab_2026-09-01.md`
- `tennis_keypoint_heldout_match_2026-09-02.md`
- `tennis_player_select_2026-09-02.md`
- `tennis_player_select_limit_2026-09-04.md`
- `tennis_probe_cleanup_2026-09-02.md`
- `tennis_resolution_controlled_2026-09-01.md`

## Headline numbers that cannot be reproduced today

Every percentage, fraction or 4-decimal rate quoted in a register row whose supporting artifact
is missing or pod-only. Denominator: 38 of 73 rows carry at least one missing artifact.

| gap | verdict | numbers quoted in the row | what is missing |
|---|---|---|---|
| G01 | AT_RISK | 35/41 | `/tmp/footage_census`, `/tmp/footage_census/run.log` |
| G03 | AT_RISK | 23.22 pct, 8/8 | `/tmp/t3_bb_harness_2026-09-01.log`, `/tmp/t3_bb_render_2026-09-01.log`, `/tmp/t3_bb_containment_2026-09-01.log` |
| G05 | AT_RISK | 10.18 pct | `/tmp/tennis-camera-lock-master` |
| G06 | AT_RISK | 0.13 | `/tmp/synthcal_wave7_refine.py`, `/tmp/synthcal_refine_run.log`, `/tmp/synthcal_judge2` |
| G10 | AT_RISK | 2/6 | `/workspace/nba-ai-system/data/footage_bridge/` |
| G14 | AT_RISK | 50 of 148 | `/workspace/keep_track_daemo`, `/workspace/track_daemon.pid`, `/tmp/g14_tennis_seq.log` |
| G19 | AT_RISK | 183 of 184, 4 pct | `/workspace/track_daemon.pid`, `/tmp/t3b_run.py`, `/tmp/t3b_reemit_2026-09-01.log` |
| G25 | AT_RISK | 6,624/32,355, 20.5 pct, 20 pct, 0.18 pct, 57.0 pct, 41.1 pct, 27.7 pct, 28.7 pct | `/tmp/t3b_reemit/` |
| G34 | AT_RISK | 0.4167, 95 pct, 0.362, 0.473 | `/tmp/tennis-camera-lock-master` |
| G36 | AT_RISK | 9 of 36 | `/workspace/nba-ai-system/data/footage_bridge/`, `/workspace/track_daemon.pid` |
| G37 | AT_RISK | 0.030 | `football__football_wHZt1eY3A9s.mp4`, `football__football_wHZt1eY3A9s_1080p.mp4`, `wnba__wnba_01.mp4` |
| G38 | AT_RISK | 7 of 8, 65 pct, 8 of 9, 6/9, 4/9 | `/workspace/track_daemon.log` |
| G41 | BROKEN | 28/28 | `harness_verdict.json`, `tracking_capability.json`, `/tmp/g42_retrack` |
| G44 | AT_RISK | 64 pct, 52 pct, 2/3, 33 pct, 12 of 12 | `/workspace/nba-ai-system/data/tracking/` |
| G46 | AT_RISK | 0.9878, 91/91, 89/91, 20/20 | `/workspace/nba-ai-system/data/tracking/` |
| G60 | AT_RISK | 5.0 pct | `/workspace/nba-ai-system/data/footage_corpus/` |
| G47 | AT_RISK | 119 of 187, 66/93, 8/12, 30/42, 15/25, 0/15 | `/workspace/nba-ai-system/data/tracking_reports/`, `/workspace/nba-ai-system/data/tracking/`, `/workspace/nba-ai-system/data/tracking/kbo_10/tracking_data.csv` |
| G48 | BROKEN | 28/187, 15.9 pct, 15.0 pct, 28 of 187, 0.0800, 0.1001, 25.1 pct | `footage_cycle_ledger.jsonl`, `/tmp/g35_probe.py`, `/tmp/g35_probe_out.json` |
| G49 | BROKEN | 0.00778, 22/25 | `footage_cycle_ledger.jsonl`, `/tmp/g35_probe.py`, `/tmp/g35_probe_out.json` |
| G50 | BROKEN | 10 of 184 | `footage_cycle_ledger.jsonl`, `/tmp/g35_probe.py`, `/tmp/g35_probe_out.json` |
| G33B | AT_RISK | 9/30, 0/6 | `/workspace/nba-ai-system/data/footage_corpus/`, `mlb__mlb_2iosUkpL0Bc.mp4`, `mlb__mlb_ARtRmUHC7dw.mp4` |

21 of 73 register rows (28.8 pct) quote at least one number that no surviving local artifact
can regenerate.

## NOT VERIFIED -- what this audit could not check, and why

1. **The pod filesystem.** Every /tmp and /workspace path was scored absent because it is
   absent HERE. No pod was reachable from this session, so I cannot say whether a given pod
   path still exists, was already destroyed by the reallocation that G54 records, or was never
   written. AT_RISK is a statement about durability, not a claim that the file is gone.
2. **Unmerged worktree commits.** `baseball_night_pitchview_2026-09-01.md` (G11, G32) is
   recorded in the register as living in worktree commit 00b9ed4de on nba-track-a7. Only the
   16 `.claude/worktrees/agent-*` worktrees are attached to this checkout; the nba-track-aN
   worktrees are not, so I could not open that commit. The memo is absent from the working
   tree, which is what A7 tests, but it may still be recoverable from that sha.
3. **Git history.** Register cells cite bare shas (G21 `1c5f1e6b7`, G09 `754b7543e`, G33
   `452c9d954`, and about 20 more). No sha was resolved; a commit-shaped citation is not a
   file, so it was scored only when it also named a path.
4. **Memo CONTENT correctness.** This audit checks that a cited path exists. It does not open
   a render and confirm it shows what the memo says, does not recompute a fraction from a csv,
   and does not check that a present artifact is the one the number was actually derived from.
   A SAFE verdict means reproducible in principle, not reproduced.
5. **Path extraction is regex-based.** Prose references without a path shape (a memo named in
   words, a `<game>` placeholder segment, a directory named only in a sentence) are invisible
   to it. The artifact counts are therefore a lower bound on what each memo depends on.
6. **The register is being edited live.** It was written at 14:10:39, 14:13:53 and 14:14:49
   local time during this audit, growing from 97,468 to 98,783 bytes and from 67 to 73 rows,
   and six new rows (G65-G70) appeared mid-sweep. The counts above are the 14:14:49 snapshot,
   which was stable across the final parse (identical mtime before and after it). The memo
   directory also grew from 84 to 89 .md files during the audit. Re-run before quoting.
7. **`data/` is gitignored and machine-local.** A `data/` artifact that resolves here is not
   evidence that it resolves on any other checkout, and the inverse holds too. That cuts both
   ways for the SAFE count.
