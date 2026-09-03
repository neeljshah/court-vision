# S173 -- direct n_eff re-quote source check

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q.
Calibration language only. This is an S-row; reproduction replaces an eye check.

## Result

S161's construct remains 45 published n_eff readouts: 22 direct RE-QUOTED rows and
23 RE-LABELLED rows. Before this pass the direct conversion metric was 0 / 23.

The stated premise is FALSIFIED at the direct-source level. All 23 legacy manifest
`source_path` summary JSON files exist (23 / 23), but none of the 23 corresponding
named per-unit input series exists in this worktree (0 / 23). The S86 CSV that is
present is not a named input for any of these 23 rows and does not reproduce one of
their stored n_eff readouts. No source was loaded beyond a bounded header or summary
inspection, and no source store over 300 MB was opened.

The after metric is therefore 0 / 23. All 23 rows remain RE-LABELLED, retain their
published summary values, and now name the absent direct source in `manifest.csv`.
No direct `effective_sample_size` invocation was valid, so no value, delta, per-unit
copy, or source hash was fabricated. There was no present direct source to append to
`source_inventory.csv`; that existing inventory is preserved.


## Per-row direct-source limit

Every listed rule is the published tick rule. Every named direct source was absent.

| readout_id | tick rule | direct source |
|---|---|---|
| S87b_S80_embargo1_precise | informative per-game eps=1e-9 plus duplicate rule | s80_player_grain_2026-09-03_s83.csv |
| S87b_S80_embargo0 | informative per-game eps=1e-9 plus duplicate rule | s80_player_grain_2026-09-03_s83.csv |
| S87b_S80_embargo1_rounded | informative per-game eps=1e-9 plus duplicate rule | s80_player_grain_2026-09-03_s83.csv |
| S137_S102 | all ticks | s102_nba_sweep_top10_series.parquet |
| S137_S82_before | all ticks | s82_ingame_screen_series_2026-09-03.csv |
| S137_S82_after | all ticks | s82_ingame_screen_series_2026-09-03.csv |
| S137_S87_before | all ticks | s58_trialA_clamp_family_series_2026-09-03.csv |
| S137_S87_after | all ticks | s58_trialA_clamp_family_series_2026-09-03.csv |
| S137_S112_nba_before | all ticks | s112_rescore_2026-09-03_nba_fullmodel_pre_s132.csv |
| S137_S112_nba_after | all ticks | s112_rescore_2026-09-03_nba_fullmodel_pre_s132.csv |
| S137_S112_mlb_before | all ticks | s112_rescore_2026-09-03_mlb_fullmodel_pre_s132.csv |
| S137_S112_mlb_after | all ticks | s112_rescore_2026-09-03_mlb_fullmodel_pre_s132.csv |
| S137_S114_before | all ticks | s114_ingame_ensemble_series.csv |
| S137_S114_after | all ticks | s114_ingame_ensemble_series.csv |
| S137_S116_before | all ticks | s116_pooled_ingame_2026-09-03.csv |
| S137_S116_after | all ticks | s116_pooled_ingame_2026-09-03_rerun.csv |
| S137_S119_before | all ticks | s119_real_game_series_2026-09-03.csv |
| S137_S119_after | all ticks | s119_real_game_series_2026-09-03.csv |
| S137_S121_before | all ticks | s119_real_game_series_2026-09-03.csv |
| S137_S121_after | all ticks | s119_real_game_series_2026-09-03.csv |
| S137_S102_recap | all ticks | s102_nba_sweep_top10_series.parquet |
| S137_S103 | all ticks | s103_nba_sigma_2026-09-03.csv |
| S137_S115 | all ticks | s115_ingame_models_2026-09-03.csv |

## NOT VERIFIED

All 23 rows above are NOT VERIFIED as direct re-quotes because their named per-unit
series are absent. This is a limit finding, not a dropped row or a substituted
summary calculation. There are no converted rows for a verifier to recompute and no
new source hashes to diff.

## Contract self-check

- B1: all 23 construct rows are named and retained; none is excluded.
- B2-B6: only evidence metadata and a new memo changed. No module, schema field,
  verdict, deployment path, ledger, or feature flag moved.
- B7/Q7: this is the exhaustive 23-row construct; S-row reproduction replaces an
  eye check.
- B8-B10/Q1-Q5/Q9: no model was fit or scored, no FWER ledger was opened, and no
  threshold moved.
- Q6: calibration language only. Q8 is satisfied by the direct-source re-measurement.

Test: `python -m pytest tests/platformkit/ingame/test_s161_neff_requote_manifest.py -q`.
