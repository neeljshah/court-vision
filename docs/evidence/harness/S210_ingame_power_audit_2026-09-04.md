# S210 - in-game power audit: FALSIFIED at the premise

Date: 2026-09-04 | Area: signals-ingame | Verdict: **FALSIFIED**

This is the required Step 0 stop memo. S210 requires the two archived paired-loss
anchors to be recomputed before an auditor can enumerate or label screens. Neither
anchor series exists in this worktree. Memo values are not substituted for a
recomputation from a Q9 series.

## Required anchor probes

The probes below were read-only path checks. An absent path has no byte size and was
not opened. No data store was read.

| anchor | required archive path | expected memo result | probe result |
|---|---|---|---|
| S82 `tick_index_in_game` | `data/cache/eval_gate/s82_ingame_screen_series_2026-09-03.csv` | 15,702 ticks; 41 game clusters; improvement +0.003332; CI [-0.001971, +0.008636] | **ABSENT** |
| S117 headline soccer screen | `data/cache/eval_gate/s117_soccer_ingame_screen_2026-09-03_series.csv` | 163 ticks; 2 game clusters | **ABSENT** |

The memo sources that name the expected values are
`docs/evidence/harness/S82_ingame_screen_2026-09-03.md` (17,943 bytes) and
`docs/evidence/harness/S117_soccer_ingame_screen_2026-09-03.md` (13,425 bytes).
They are evidence descriptions, not the archived per-tick differentials required
to calculate a paired-loss standard error, n_eff, or 80 percent-power MDE.

## Stop boundary

S210 says: if either anchor fails, STOP, write this memo, commit FALSIFIED. Both
required anchors fail because their Q9 CSVs are unavailable here. Therefore this
lane did not run the required grep enumeration, did not create the read-only
auditor or its test, did not calculate MDEs, and did not assign UNDERPOWERED or
REFUTED-AT-BAR labels. Reporting a denominator or a power label without the
series would be circular.

No existing memo or artifact was edited. The frozen +0.004 in-game bar is unchanged.
No register, ledger, `data/` path, feature flag, or production path was touched.

## NOT VERIFIED

The full in-game screen enumeration, per-screen n_ticks, game-cluster count, n_eff,
paired-loss standard errors, MDEs, and power labels remain NOT VERIFIED until the
two required Q9 archives are present in the same worktree. This memo makes no
calibration finding beyond the failed reproducibility premise.

## ATTEMPT_2B_CORRECTIONS (alias: S210_ATTEMPT_2B_2026_09_04)

This dated additive section records the corrected literal enumeration, archived
paired-loss improvement and CI95 power audit. The original FALSIFIED memo above is
preserved byte-for-byte as the parent record.

### ATTEMPT_2_STORE_VISIBILITY_ARTEFACT

Attempt 1 reported FALSIFIED because the two Q9 archives were not visible in
that process. This fresh process opened the read-only archived series and
reproduced both anchors; it does not alter the parent record above.

### ATTEMPT_2B_CORRECTIONS

The auditor imports and calls `effective_sample_size` from
`scripts/platformkit/ingame/gap_effective_n.py`, so n_eff includes its
unequal-cluster correction. It derives the denominator directly from this
literal predicate, not from a screen list:

```powershell
Get-ChildItem docs/evidence/harness -Filter 'S*.md' | ForEach-Object {
  $t = Get-Content -Raw $_.FullName
  if ($t -match '(?i)in-game|ingame' -and $t -match '(?i)improvement' -and
      $t -match '(?i)(ci95|confidence interval|DM 95)') { $_.Name }
}
```

The predicate returned the 29 source memos below. Each row is retained in the
denominator. A memo without an own unambiguous paired Brier archive reports its
explicit NO SERIES ARCHIVED reason; it is not silently excluded. MDE80 is
`(t_0.975,G-1 + t_0.80,G-1) * paired_loss_se`; the frozen bar is +0.004.

| source memo (without .md) | n_ticks | clusters | n_eff | improvement | CI95 half | MDE80 | label |
|---|---:|---:|---:|---:|---:|---:|---|
| S06_stacker_result_2026-09-03 | 47,104 | 158 | 296.610988 | +0.090156835811 | 0.042094316591 | 0.060079477584 | UNDERPOWERED |
| S08_replication_gate_2026-09-03 | - | - | - | - | - | - | NO SERIES ARCHIVED: no readable paired-series archive |
| S100_microstructure_2026-09-03 | - | - | - | - | - | - | NO SERIES ARCHIVED: no unambiguous paired Brier differential |
| S102_nba_pod_sweep_2026-09-03 | 1,926,350 | 673 | 11,149.499351 | +0.000162316390 | 0.000196387261 | 0.000280618869 | REFUTED-AT-BAR |
| S103_nba_sigma_2026-09-03 | - | - | - | - | - | - | NO SERIES ARCHIVED: no unambiguous paired Brier differential |
| S114_ingame_ensemble_2026-09-03 | - | - | - | - | - | - | NO SERIES ARCHIVED: no unambiguous paired Brier differential |
| S116_pooled_ingame_2026-09-03 | - | - | - | - | - | - | NO SERIES ARCHIVED: no unambiguous paired Brier differential |
| S117_soccer_ingame_screen_2026-09-03 | 163 | 2 | 14.681646 | +0.025071328021 | 0.362929445877 | 0.402243272317 | UNDERPOWERED |
| S119_mlb_ingame_supply_2026-09-03 | 15,702 | 88 | 120.717204 | +0.003332296267 | 0.007037559872 | 0.010032200743 | UNDERPOWERED |
| S121_tick_partition_2026-09-03 | - | - | - | - | - | - | NO SERIES ARCHIVED: no readable paired-series archive |
| S124_S125_S126_S131_ingame_guards_2026-09-03 | - | - | - | - | - | - | NO SERIES ARCHIVED: no readable paired-series archive |
| S126_rerun_S124_gate_2026-09-03 | - | - | - | - | - | - | NO SERIES ARCHIVED: no readable paired-series archive |
| S137_rebaseline_2026-09-03 | - | - | - | - | - | - | NO SERIES ARCHIVED: no readable paired-series archive |
| S148_live_requote_2026-09-03 | - | - | - | - | - | - | NO SERIES ARCHIVED: no readable paired-series archive |
| S152_s116_rerun_2026-09-03 | - | - | - | - | - | - | NO SERIES ARCHIVED: no readable paired-series archive |
| S210_ingame_power_audit_2026-09-04 | - | - | - | - | - | - | NO SERIES ARCHIVED: no readable paired-series archive |
| S58_trial1_e2_slice_2026-09-03 | 6,579 | 157 | 467.272882 | +0.048272196858 | 0.023850415315 | 0.034040382412 | UNDERPOWERED |
| S58_trialA_clamp_family_2026-09-03 | 47,104 | 158 | 566.181701 | -0.000866166276 | 0.001230029883 | 0.001755570794 | REFUTED-AT-BAR |
| S58_trialB_nba_halftime_asof_2026-09-03 | - | - | - | - | - | - | NO SERIES ARCHIVED: no readable paired-series archive |
| S79_family_combo_2026-09-03 | 800 | 30 | 800.000000 | -0.003873663613 | 0.004824678573 | 0.006839709886 | UNDERPOWERED |
| S80_player_grain_2026-09-03 | 2,267 | 13 | 79.251785 | +0.003759465553 | 0.030638865461 | 0.042909657298 | UNDERPOWERED |
| S81_market_move_2026-09-03 | - | - | - | - | - | - | NO SERIES ARCHIVED: no readable paired-series archive |
| S82_ingame_screen_2026-09-03 | 15,702 | 41 | 214.827112 | +0.003332296267 | 0.005303660238 | 0.007536047364 | UNDERPOWERED |
| S83_mlb_join_player_ids_2026-09-03 | - | - | - | - | - | - | NO SERIES ARCHIVED: no readable paired-series archive |
| S86_nba_every_tick_2026-09-03 | 232,951 | 797 | 3,260.070012 | -0.004856640630 | 0.002497941012 | 0.003569517036 | REFUTED-AT-BAR |
| S94_nba_early_shrinkage_2026-09-03 | - | - | - | - | - | - | NO SERIES ARCHIVED: no unambiguous paired Brier differential |
| S96_nba_overreaction_2026-09-03 | - | - | - | - | - | - | NO SERIES ARCHIVED: no unambiguous paired Brier differential |
| S97_nba_sensor_fusion_2026-09-03 | - | - | - | - | - | - | NO SERIES ARCHIVED: no unambiguous paired Brier differential |
| S98_nba_better_prior_2026-09-03 | - | - | - | - | - | - | NO SERIES ARCHIVED: no unambiguous paired Brier differential |

Denominator: 29 literal-predicate memos. Power labels: 7 UNDERPOWERED, 3
REFUTED-AT-BAR, 0 SUPPORTED, and 19 NO SERIES ARCHIVED. The machine-readable
summary is `docs/evidence/harness/S210_ingame_power_audit_2026-09-04.json`.

## Fresh-process premise anchors

| anchor | fresh archived-series reproduction | result |
|---|---|---|
| S82 `tick_index_in_game` | 15,702 ticks / 41 clusters / +0.003332296267 / CI [-0.001971363972, +0.008635956505] | PASS; maximum absolute difference at most 1e-9 |
| S117 `minute_x_score_diff` | 163 ticks / 2 clusters / +0.025071328021 | PASS; required denominator reproduces |

## NOT VERIFIED

- No original memo verdict is changed, rescored, or promoted by this archival
  power classification.
- The 19 NO SERIES ARCHIVED rows do not have an own unambiguous paired Brier
  differential in their linked archive surface; they remain visible in the 29.
- This does not add a corpus, model, threshold, or decision beyond the frozen
  +0.004 calibration bar.
- The FWER ledger, hypotheses database, register, and feature flags remain
  unread or unchanged.

## Verification

Fresh-process regeneration: `python -m scripts.platformkit.eval_gate.s210_power_audit --json docs/evidence/harness/S210_ingame_power_audit_2026-09-04.json`.
`python -m pytest scripts/platformkit/eval_gate/test_s210_power_audit.py -q -p no:cacheprovider` -> 4 passed.
`python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider` -> 1 passed.
