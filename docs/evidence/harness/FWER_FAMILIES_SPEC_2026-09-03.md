# FWER families -- FROZEN prereg (S14)

spec_version: s102-families-v3
frozen_on: 2026-09-03
amended_on: 2026-09-03 (S89 -- two in-game ARM families added; nothing removed, no bar moved)
amended_on: 2026-09-03 (S102 -- one NBA in-game TICK-GRID family added; nothing removed, no bar moved)
q_within_family: 0.05
alpha_global: 0.05
families: 40
feature_grid_families: 37
arm_families: 2
tick_grid_families: 1
features: 423
hypotheses: 4151
transform_grid: raw, ew(halflife=3), ew(halflife=5), ew(halflife=10), ew(halflife=20), rank_in_league, z_vs_league, delta_vs_prior, ratio_to_opponent
transform_instances: 9
conditioning: empty set (SF-16 freezes v1 conditioning to {}) for the 37 feature grids; the
  S102 tick grid declares its own closed conditioning alphabet in its block below

THIS FILE IS FROZEN. It is the family partition used by
`scripts/platformkit/eval_gate/family_bars.py`, which pins it by `git hash-object`
and embeds that blob id in every verdict it prints. Editing this file changes the
blob id, so a verdict priced against an older partition is self-evidently stale.
It is COMMITTED BEFORE the first family-relative trial is ever run.

WHAT THIS DOCUMENT LOOSENS. Until S14 every hypothesis was priced by
`deflated_metrics.deflated_p(raw_p, k_global)` -- Bonferroni across the whole
cumulative trial ledger, i.e. as if all hypotheses were independent and all in one
family. A within-family Benjamini-Hochberg bar at q=0.05 is strictly LOOSER than
that for a hypothesis inside a large family. The loosening is admissible only
under the three conditions written in the S14 spec, and this file discharges the
first of them. No verdict recorded before this file's commit may be re-scored
under the family bar; `family_bars.dual_bar_verdict` takes p-values as arguments
and never reads a historical ledger row, so re-scoring is impossible by
construction.

## Family construction rule (mechanical, reproducible)

A family is one (sport, column-set) group over `scripts/platformkit/foundry/catalogue.py`
`entries()` -- every catalogue parquet PRESENT on disk on 2026-09-03. Two parquets whose
column NAMES are identical are the same feature grid and therefore one family (this is what
collapses the four `opp_allowed_asof_*` season files, the seven `soccer_states__*` league
files and the ATP/WTA `asof_setdetail` pair into one family each).

A column is a MEMBER (a modelable feature) when it is numeric-dtyped AND its name is not
`y`, `season` or `minute`, and does not end in `_n_prior` or `_id`. Non-numeric dtypes drop
ids, dates and label strings; the named exclusions drop the label, the season key, the
match-clock key and the prior-count denominators.

hypotheses = members x 9 transform instances x 1 horizon x 1 market x {} conditioning.

horizon/market are frozen labels, not measurements: a family sourced from
`data/cache/ingame/` is (live_tick, inplay); `asof_inning` is (period, total) and
`asof_quarter_shape` is (period, spread); everything else is pregame, with market `ml`
(nba, mlb, tennis), `total` (soccer), or `prop` for `nba_opp_allowed` and `nba_player_adv`.

## Arm-family construction rule (S89 amendment, 2026-09-03)

The 37 families above are FEATURE GRIDS. Eleven of them carry (live_tick, inplay), but a
feature grid is not an arm: an in-game ARM is a whole scored predictor (a blend config, a
checkpoint pricer), so the 9-transform grid does not apply to it and
`hypotheses = features` for an arm family, one hypothesis per arm. `features` still equals
`len(members)`, so `family_bars.load_families` parses an arm family with no code change beyond the OPTIONAL
`kind:` field, which is `grid` by default so all 37 original blocks stay byte-identical.
An enumerator that walks members as COLUMNS (`foundry/seed_queue.frozen_hypotheses`) skips
`kind: arm`, so the frozen 9-transform grammar still enumerates exactly 3,564 hypotheses.

S102 adds ONE `kind: tickgrid` family, `ingame_nba_tickgrid`. The NBA in-play tick corpus
carries only score / period / clock / margin / market / outcome per tick, so its hypotheses
are DERIVED state, not stored columns, and the 9-transform pregame alphabet does not apply:
three of its nine transforms (rank_in_league, z_vs_league, ratio_to_opponent) need league or
opponent tables that do not exist at tick grain. The tick grid therefore declares its own
CLOSED construction rule in its block -- 16 base columns x 6 transforms x 6 conditionings =
576 -- enumerated by `foundry/ingame_grammar_nba.enumerate_hypotheses` and deduped by
`grammar.semantic_hash`. Like `kind: arm`, it is SKIPPED by
`foundry/seed_queue.frozen_hypotheses`, so the frozen 9-transform grammar still enumerates
exactly 3,564 pregame hypotheses. It is committed BEFORE the S102 screen is run.

S89 adds ONE arm family per sport that has an in-game arm on disk. Two qualify:
`ingame_arms_mlb` and `ingame_arms_nba`. There is NO soccer arm family: no soccer in-game
arm exists in `scripts/platformkit/ingame/` and none has ever been charged, and a family
invented for a sport with no arm is a family invented after the fact.

Three in-game charges were made BEFORE this amendment, as families of one outside the
partition: `ingame_mlb_arms` (k_cumulative 15), `ingame_mlb_clamp` (16) and
`ingame_nba_halftime_asof` (17). `family_bars.FAMILY_ALIASES` maps those three historical
strings onto the two new families so within-family K counts them retroactively. The ledger
`data/cache/eval_gate/backtest_fwer.jsonl` is NOT rewritten -- every row keeps the string it
was charged with -- and NO recorded verdict is re-scored: the three stay labelled
family-of-one in their own artifacts, exactly as condition (iii) requires.

## Not in this partition

Five NAMED catalogue paths are absent from disk and therefore define NO family:
- `data/domains/soccer/asof_discipline_features.parquet`
- `data/domains/tennis/asof_features_wta.parquet`
- `data/domains/tennis/asof_return_wta.parquet`
- `data/domains/tennis/asof_meta_wta.parquet`
- `data/domains/tennis/schedule_density_wta.parquet`

## Reconciliation with the red-team draft

`docs/evidence/harness/REDTEAM_SIGNAL_FACTORY_2026-09-03.md` section 4 drafted 34 families /
376 features / 3,384 hypotheses by hand. The measured partition below is 37 families /
396 features / 3564 hypotheses. The draft is superseded: it omitted the in-game MLB and
NBA play-by-play state grids that are on disk, and its per-family feature counts were counted
by eye rather than by the dtype rule above.

## Summary

| family | sport | horizon | market | features | hypotheses |
|---|---|---|---|---|---|
| ingame_arms_mlb | mlb | live_tick | inplay | 10 | 10 |
| ingame_arms_nba | nba | live_tick | inplay | 1 | 1 |
| ingame_nba_tickgrid | nba | live_tick | inplay | 16 | 576 |
| mlb_atbat_states | mlb | live_tick | inplay | 10 | 90 |
| mlb_bullpen_relief_chains | mlb | pregame | ml | 6 | 54 |
| mlb_catcher_framing_index | mlb | pregame | ml | 3 | 27 |
| mlb_gate | mlb | pregame | ml | 5 | 45 |
| mlb_inning | mlb | period | total | 6 | 54 |
| mlb_pitch_states | mlb | live_tick | inplay | 16 | 144 |
| mlb_states | mlb | live_tick | inplay | 8 | 72 |
| nba_boxdetail | nba | pregame | ml | 30 | 270 |
| nba_carryover | nba | pregame | ml | 6 | 54 |
| nba_defender_rollup | nba | pregame | ml | 18 | 162 |
| nba_gate | nba | pregame | ml | 11 | 99 |
| nba_opp_allowed | nba | pregame | prop | 15 | 135 |
| nba_pbp_foul_states | nba | live_tick | inplay | 9 | 81 |
| nba_pbp_states | nba | live_tick | inplay | 6 | 54 |
| nba_player_adv | nba | pregame | prop | 6 | 54 |
| nba_player_value_features | nba | pregame | ml | 4 | 36 |
| nba_possession_states | nba | live_tick | inplay | 13 | 117 |
| nba_quarter_shape | nba | period | spread | 15 | 135 |
| nba_team_adv | nba | pregame | ml | 27 | 243 |
| soccer_cardstates | soccer | live_tick | inplay | 7 | 63 |
| soccer_gate | soccer | pregame | total | 10 | 90 |
| soccer_referee_card_foul_profiles | soccer | pregame | total | 5 | 45 |
| soccer_shotstates | soccer | live_tick | inplay | 5 | 45 |
| soccer_shotxgstates | soccer | live_tick | inplay | 5 | 45 |
| soccer_states | soccer | live_tick | inplay | 7 | 63 |
| soccer_style_fingerprints | soccer | pregame | total | 14 | 126 |
| soccer_xg_proxy | soccer | pregame | total | 9 | 81 |
| tennis_features | tennis | pregame | ml | 15 | 135 |
| tennis_gate | tennis | pregame | ml | 6 | 54 |
| tennis_hold | tennis | pregame | ml | 16 | 144 |
| tennis_meta | tennis | pregame | ml | 12 | 108 |
| tennis_return | tennis | pregame | ml | 18 | 162 |
| tennis_schedule_density | tennis | pregame | ml | 4 | 36 |
| tennis_serve_return_profiles | tennis | pregame | ml | 5 | 45 |
| tennis_setdetail | tennis | pregame | ml | 36 | 324 |
| tennis_states | tennis | live_tick | inplay | 5 | 45 |
| tennis_travel_scouting | tennis | pregame | ml | 3 | 27 |

## Families

### fam: ingame_arms_mlb
kind: arm
sport: mlb
horizon: live_tick
market: inplay
features: 10
hypotheses: 10
sources: scripts/platformkit/eval_gate/s58_e2_slice_trial.py, scripts/platformkit/eval_gate/s58_clamp_family_trial.py
members: e2_gd, e4_gd, e4_w0.5_d0.10, e4_w1.0_d0.10, e4_w2.0_d0.10, e4_w0.5_d0.15, e4_w2.0_d0.15, e4_w0.5_d0.25, e4_w1.0_d0.25, e4_w2.0_d0.25

### fam: ingame_arms_nba
kind: arm
sport: nba
horizon: live_tick
market: inplay
features: 1
hypotheses: 1
sources: scripts/platformkit/eval_gate/s58_nba_halftime_asof_trial.py
members: nba_halftime_asof

### fam: ingame_nba_tickgrid
kind: tickgrid
sport: nba
horizon: live_tick
market: inplay
features: 16
hypotheses: 576
sources: data/cache/inplay_odds/nba_checkpoints_full.parquet, data/cache/eval_gate/s86_nba_every_tick_2026-09-03.csv
members: margin, rem, dmargin_k3, dmargin_k5, dmargin_k10, dmargin_k20, run_len_signed, lead_changes, lead_change_rate, pace_total, pace_ratio_p1, tdm_h60, tdm_h180, tdm_h600, margin_x_rem, margin_over_sqrt_rem
construction: 16 base columns x 6 transforms (raw, ew(halflife=3,5,10,20), delta_vs_prior) x 6 conditionings (unconditional, phase=1..5) = 576, deduped by grammar.semantic_hash
enumerator: scripts/platformkit/foundry/ingame_grammar_nba.enumerate_hypotheses

### fam: mlb_atbat_states
sport: mlb
horizon: live_tick
market: inplay
features: 10
hypotheses: 90
sources: data/cache/ingame/mlb_atbat_states__2022.parquet, data/cache/ingame/mlb_atbat_states__2023.parquet
members: asof_idx, state_diff, frac_elapsed, p0, outcome, count_balls, count_strikes, runners, outs, base_run_value

### fam: mlb_bullpen_relief_chains
sport: mlb
horizon: pregame
market: ml
features: 6
hypotheses: 54
sources: data/domains/mlb/bullpen_relief_chains.parquet
members: game_pk, year, battersFaced, rest_days, is_b2b, appearances_last_3d

### fam: mlb_catcher_framing_index
sport: mlb
horizon: pregame
market: ml
features: 3
hypotheses: 27
sources: data/domains/mlb/catcher_framing_index.parquet
members: n_ooz_called, ooz_strikes, ooz_strike_rate

### fam: mlb_gate
sport: mlb
horizon: pregame
market: ml
features: 5
hypotheses: 45
sources: data/cache/combo/gate_corpus_mlb.parquet
members: p_base, p_home_elo, sp_first6_diff_ew, park_factor, sp_ra_diff_asof

### fam: mlb_inning
sport: mlb
horizon: period
market: total
features: 6
hypotheses: 54
sources: data/domains/mlb/asof_inning.parquet
members: home_early_rate_asof, away_early_rate_asof, early_rate_diff_asof, home_late_rate_asof, away_late_rate_asof, late_rate_diff_asof

### fam: mlb_pitch_states
sport: mlb
horizon: live_tick
market: inplay
features: 16
hypotheses: 144
sources: data/cache/ingame/mlb_pitch_states__2022.parquet, data/cache/ingame/mlb_pitch_states__2023.parquet, data/cache/ingame/mlb_pitch_states__2024.parquet, data/cache/ingame/mlb_pitch_states__2025.parquet, data/cache/ingame/mlb_pitch_states__2026.parquet
members: asof_idx, state_diff, frac_elapsed, p0, outcome, count_balls, count_strikes, runners, outs, atbat_pitch_number, pitch_velocity, pitch_loc_x, pitch_loc_y, sp_pitch_count_prior, velo_decline_vs_early, base_run_value

### fam: mlb_states
sport: mlb
horizon: live_tick
market: inplay
features: 8
hypotheses: 72
sources: data/cache/ingame/mlb_states__2021.parquet, data/cache/ingame/mlb_states__2022.parquet, data/cache/ingame/mlb_states__2023.parquet, data/cache/ingame/mlb_states__2024.parquet
members: asof_idx, state_diff, frac_elapsed, p0, outcome, runners, outs, base_out_known

### fam: nba_boxdetail
sport: nba
horizon: pregame
market: ml
features: 30
hypotheses: 270
sources: data/domains/basketball_nba/boxdetail_asof.parquet
members: home_fast_break_pts_asof, away_fast_break_pts_asof, fast_break_pts_diff_asof, home_paint_pts_asof, away_paint_pts_asof, paint_pts_diff_asof, home_tov_pts_asof, away_tov_pts_asof, tov_pts_diff_asof, home_largest_lead_asof, away_largest_lead_asof, largest_lead_diff_asof, home_foul_trouble_asof, away_foul_trouble_asof, foul_trouble_diff_asof, home_fast_break_pts_l10_asof, away_fast_break_pts_l10_asof, fast_break_pts_l10_diff_asof, home_paint_pts_l10_asof, away_paint_pts_l10_asof, paint_pts_l10_diff_asof, home_tov_pts_l10_asof, away_tov_pts_l10_asof, tov_pts_l10_diff_asof, home_largest_lead_l10_asof, away_largest_lead_l10_asof, largest_lead_l10_diff_asof, home_foul_trouble_l10_asof, away_foul_trouble_l10_asof, foul_trouble_l10_diff_asof

### fam: nba_carryover
sport: nba
horizon: pregame
market: ml
features: 6
hypotheses: 54
sources: data/domains/basketball_nba/carryover_asof.parquet
members: home_heavy_min_load_asof, away_heavy_min_load_asof, heavy_min_load_diff_asof, home_rest_days_asof, away_rest_days_asof, rest_days_diff_asof

### fam: nba_defender_rollup
sport: nba
horizon: pregame
market: ml
features: 18
hypotheses: 162
sources: data/domains/basketball_nba/asof_defender_rollup.parquet
members: home_def_fg_pct_allowed_asof, away_def_fg_pct_allowed_asof, def_fg_pct_allowed_diff_asof, home_def_fg3_pct_allowed_asof, away_def_fg3_pct_allowed_asof, def_fg3_pct_allowed_diff_asof, home_def_pts_allowed_per36_asof, away_def_pts_allowed_per36_asof, def_pts_allowed_per36_diff_asof, home_def_blocks_per_game_asof, away_def_blocks_per_game_asof, def_blocks_per_game_diff_asof, home_def_switches_per_game_asof, away_def_switches_per_game_asof, def_switches_per_game_diff_asof, home_def_matchup_min_asof, away_def_matchup_min_asof, def_matchup_min_diff_asof

### fam: nba_gate
sport: nba
horizon: pregame
market: ml
features: 11
hypotheses: 99
sources: data/cache/combo/gate_corpus_nba.parquet
members: p_base, p_elo, dreb_diff_asof, fg3m_diff_asof, stl_diff_asof, blk_diff_asof, pace_diff_asof, oreb_pg_diff_asof, tov_pg_diff_asof, dreb_x_pace_asof, stl_x_fg3m_asof

### fam: nba_opp_allowed
sport: nba
horizon: pregame
market: prop
features: 15
hypotheses: 135
sources: data/cache/pit/opp_allowed_asof_2023_24.parquet, data/cache/pit/opp_allowed_asof_2024_25.parquet, data/cache/pit/opp_allowed_asof_2025_26_reg.parquet, data/cache/pit/opp_allowed_asof_2026_playoffs.parquet
members: opp_pts_allowed_asof, opp_reb_allowed_asof, opp_ast_allowed_asof, opp_fg3m_allowed_asof, opp_stl_allowed_asof, opp_blk_allowed_asof, opp_tov_allowed_asof, n_games_asof, opp_pts_allowed_vs_league, opp_reb_allowed_vs_league, opp_ast_allowed_vs_league, opp_fg3m_allowed_vs_league, opp_stl_allowed_vs_league, opp_blk_allowed_vs_league, opp_tov_allowed_vs_league

### fam: nba_pbp_foul_states
sport: nba
horizon: live_tick
market: inplay
features: 9
hypotheses: 81
sources: data/cache/ingame/pbp_foul_states_2024_25.parquet, data/cache/ingame/pbp_foul_states_2025_26.parquet
members: seconds_remaining, home_margin, home_fouls, away_fouls, foul_diff, home_final, away_final, home_win, n_plays_seen

### fam: nba_pbp_states
sport: nba
horizon: live_tick
market: inplay
features: 6
hypotheses: 54
sources: data/cache/ingame/pbp_states_2024_25.parquet, data/cache/ingame/pbp_states_2025_26.parquet
members: seconds_remaining, home_margin, home_final, away_final, home_win, n_plays_seen

### fam: nba_player_adv
sport: nba
horizon: pregame
market: prop
features: 6
hypotheses: 54
sources: data/domains/basketball_nba/asof_player_adv.parquet
members: usagepercentage_asof, offensiverating_asof, defensiverating_asof, pie_asof, possessions_asof, n_prior

### fam: nba_player_value_features
sport: nba
horizon: pregame
market: ml
features: 4
hypotheses: 36
sources: data/domains/basketball_nba/player_value_features.parquet
members: roster_value_asof, star_absence_delta, continuity, top_heavy

### fam: nba_possession_states
sport: nba
horizon: live_tick
market: inplay
features: 13
hypotheses: 117
sources: data/cache/ingame/possession_states_2024_25.parquet, data/cache/ingame/possession_states_2025_26.parquet
members: asof_idx, seconds_remaining, frac_elapsed, state_diff, home_margin, possessions_elapsed, pace_so_far, run_diff, poss_since_lead_change, home_final, away_final, outcome, n_plays_seen

### fam: nba_quarter_shape
sport: nba
horizon: period
market: spread
features: 15
hypotheses: 135
sources: data/domains/basketball_nba/asof_quarter_shape.parquet
members: home_q1_margin_asof, away_q1_margin_asof, diff_q1_margin_asof, home_first_half_margin_asof, away_first_half_margin_asof, diff_first_half_margin_asof, home_second_half_margin_asof, away_second_half_margin_asof, diff_second_half_margin_asof, home_q4_margin_asof, away_q4_margin_asof, diff_q4_margin_asof, home_quarter_volatility_asof, away_quarter_volatility_asof, diff_quarter_volatility_asof

### fam: nba_team_adv
sport: nba
horizon: pregame
market: ml
features: 27
hypotheses: 243
sources: data/domains/basketball_nba/asof_team_adv.parquet
members: home_off_rtg_asof, away_off_rtg_asof, off_rtg_diff_asof, home_def_rtg_asof, away_def_rtg_asof, def_rtg_diff_asof, home_pace_asof, away_pace_asof, pace_diff_asof, home_oreb_pct_asof, away_oreb_pct_asof, oreb_pct_diff_asof, home_dreb_pct_asof, away_dreb_pct_asof, dreb_pct_diff_asof, home_ast_pct_asof, away_ast_pct_asof, ast_pct_diff_asof, home_efg_pct_asof, away_efg_pct_asof, efg_pct_diff_asof, home_ts_pct_asof, away_ts_pct_asof, ts_pct_diff_asof, home_tov_ratio_asof, away_tov_ratio_asof, tov_ratio_diff_asof

### fam: soccer_cardstates
sport: soccer
horizon: live_tick
market: inplay
features: 7
hypotheses: 63
sources: data/cache/ingame/soccer_cardstates__combo_eng_ger.parquet, data/cache/ingame/soccer_cardstates__combo_esp_ita.parquet
members: asof_idx, red_diff, yellow_diff, sub_count_diff, shot_zone_diff, home_reds, away_reds

### fam: soccer_gate
sport: soccer
horizon: pregame
market: total
features: 10
hypotheses: 90
sources: data/cache/combo/gate_corpus_soccer.parquet
members: p_base, p_over25, home_sot_for_l10, away_sot_for_l10, diff_sot_for_asof, diff_sot_against_asof, diff_shots_for_asof, diff_shots_against_asof, home_sot_ratio_for_asof, away_sot_ratio_for_asof

### fam: soccer_referee_card_foul_profiles
sport: soccer
horizon: pregame
market: total
features: 5
hypotheses: 45
sources: data/domains/soccer/referee_card_foul_profiles.parquet
members: year, total_fouls, total_yellow, total_red, total_cards

### fam: soccer_shotstates
sport: soccer
horizon: live_tick
market: inplay
features: 5
hypotheses: 45
sources: data/cache/ingame/soccer_shotstates__eng1.parquet, data/cache/ingame/soccer_shotstates__esp1.parquet, data/cache/ingame/soccer_shotstates__ger1.parquet, data/cache/ingame/soccer_shotstates__ita1.parquet
members: asof_idx, shot_diff, xgproxy_diff, home_shots, away_shots

### fam: soccer_shotxgstates
sport: soccer
horizon: live_tick
market: inplay
features: 5
hypotheses: 45
sources: data/cache/ingame/soccer_shotxgstates__combo_eng_ger.parquet, data/cache/ingame/soccer_shotxgstates__combo_esp_ita.parquet, data/cache/ingame/soccer_shotxgstates__eng1.parquet, data/cache/ingame/soccer_shotxgstates__esp1.parquet, data/cache/ingame/soccer_shotxgstates__ger1.parquet, data/cache/ingame/soccer_shotxgstates__ita1.parquet
members: asof_idx, xgloc_diff, home_xgloc, away_xgloc, n_shots_loc

### fam: soccer_states
sport: soccer
horizon: live_tick
market: inplay
features: 7
hypotheses: 63
sources: data/cache/ingame/soccer_states__combo_eng_ger.parquet, data/cache/ingame/soccer_states__combo_esp_ita.parquet, data/cache/ingame/soccer_states__eng1.parquet, data/cache/ingame/soccer_states__esp1.parquet, data/cache/ingame/soccer_states__ger1.parquet, data/cache/ingame/soccer_states__ita1.parquet, data/cache/ingame/soccer_states__wc_2026.parquet
members: asof_idx, state_diff, frac_elapsed, p0, outcome, home_goals, away_goals

### fam: soccer_style_fingerprints
sport: soccer
horizon: pregame
market: total
features: 14
hypotheses: 126
sources: data/domains/soccer/style_fingerprints.parquet
members: shot_share, sot_ratio, fouls_committed_pm, fouls_drawn_pm, corners_pm, cards_pm, ppg, n_matches, z_shot_share, z_sot_ratio, z_fouls_committed_pm, z_fouls_drawn_pm, z_corners_pm, z_cards_pm

### fam: soccer_xg_proxy
sport: soccer
horizon: pregame
market: total
features: 9
hypotheses: 81
sources: data/domains/soccer/asof_xg_proxy.parquet
members: home_xg_for_asof, away_xg_for_asof, diff_xg_for_asof, home_xg_against_asof, away_xg_against_asof, diff_xg_against_asof, home_xg_supremacy_asof, away_xg_supremacy_asof, diff_xg_supremacy_asof

### fam: tennis_features
sport: tennis
horizon: pregame
market: ml
features: 15
hypotheses: 135
sources: data/domains/tennis/asof_features.parquet
members: p1_ace_rate_asof, p1_1st_in_asof, p1_1st_win_asof, p1_2nd_win_asof, p1_bp_saved_asof, p2_ace_rate_asof, p2_1st_in_asof, p2_1st_win_asof, p2_2nd_win_asof, p2_bp_saved_asof, diff_ace_rate_asof, diff_1st_in_asof, diff_1st_win_asof, diff_2nd_win_asof, diff_bp_saved_asof

### fam: tennis_gate
sport: tennis
horizon: pregame
market: ml
features: 6
hypotheses: 54
sources: data/cache/combo/gate_corpus_tennis.parquet
members: p_base, p_elo, p1_hold_pct_asof, p2_hold_pct_asof, diff_return_won_asof, diff_break_pct_asof

### fam: tennis_hold
sport: tennis
horizon: pregame
market: ml
features: 16
hypotheses: 144
sources: data/domains/tennis/asof_hold.parquet, data/domains/tennis/asof_hold_wta.parquet
members: p1_hold_pct_asof, p1_svpts_won_asof, p2_hold_pct_asof, p2_svpts_won_asof, p1_hold_pct_hard_asof, p1_hold_pct_clay_asof, p1_hold_pct_grass_asof, p2_hold_pct_hard_asof, p2_hold_pct_clay_asof, p2_hold_pct_grass_asof, p1_svpts_won_hard_asof, p1_svpts_won_clay_asof, p1_svpts_won_grass_asof, p2_svpts_won_hard_asof, p2_svpts_won_clay_asof, p2_svpts_won_grass_asof

### fam: tennis_meta
sport: tennis
horizon: pregame
market: ml
features: 12
hypotheses: 108
sources: data/domains/tennis/asof_meta.parquet
members: p1_ht, p2_ht, diff_ht, p1_rank_points, p2_rank_points, diff_rank_points, p1_seed, p2_seed, draw_size, p1_minutes_prior_asof, p2_minutes_prior_asof, diff_minutes_prior_asof

### fam: tennis_return
sport: tennis
horizon: pregame
market: ml
features: 18
hypotheses: 162
sources: data/domains/tennis/asof_return.parquet
members: p1_return_won_asof, p2_return_won_asof, diff_return_won_asof, p1_return_won_hard_asof, p2_return_won_hard_asof, p1_return_won_clay_asof, p2_return_won_clay_asof, p1_return_won_grass_asof, p2_return_won_grass_asof, p1_break_pct_asof, p2_break_pct_asof, diff_break_pct_asof, p1_break_pct_hard_asof, p2_break_pct_hard_asof, p1_break_pct_clay_asof, p2_break_pct_clay_asof, p1_break_pct_grass_asof, p2_break_pct_grass_asof

### fam: tennis_schedule_density
sport: tennis
horizon: pregame
market: ml
features: 4
hypotheses: 36
sources: data/domains/tennis/schedule_density.parquet
members: year, rest_days, matches_last_7d, matches_last_14d

### fam: tennis_serve_return_profiles
sport: tennis
horizon: pregame
market: ml
features: 5
hypotheses: 45
sources: data/domains/tennis/serve_return_profiles.parquet
members: serve_strength, return_strength, n_matches, z_serve_strength, z_return_strength

### fam: tennis_setdetail
sport: tennis
horizon: pregame
market: ml
features: 36
hypotheses: 324
sources: data/domains/tennis/asof_setdetail.parquet, data/domains/tennis/asof_setdetail_wta.parquet
members: p1_tiebreak_win_pct_asof, p1_sets_dropped_rate_asof, p1_close_set_rate_asof, p1_avg_games_per_set_asof, p2_tiebreak_win_pct_asof, p2_sets_dropped_rate_asof, p2_close_set_rate_asof, p2_avg_games_per_set_asof, p1_tiebreak_win_pct_hard_asof, p1_tiebreak_win_pct_clay_asof, p1_tiebreak_win_pct_grass_asof, p1_sets_dropped_rate_hard_asof, p1_sets_dropped_rate_clay_asof, p1_sets_dropped_rate_grass_asof, p1_close_set_rate_hard_asof, p1_close_set_rate_clay_asof, p1_close_set_rate_grass_asof, p1_avg_games_per_set_hard_asof, p1_avg_games_per_set_clay_asof, p1_avg_games_per_set_grass_asof, p2_tiebreak_win_pct_hard_asof, p2_tiebreak_win_pct_clay_asof, p2_tiebreak_win_pct_grass_asof, p2_sets_dropped_rate_hard_asof, p2_sets_dropped_rate_clay_asof, p2_sets_dropped_rate_grass_asof, p2_close_set_rate_hard_asof, p2_close_set_rate_clay_asof, p2_close_set_rate_grass_asof, p2_avg_games_per_set_hard_asof, p2_avg_games_per_set_clay_asof, p2_avg_games_per_set_grass_asof, tiebreak_win_pct_asof_diff, sets_dropped_rate_asof_diff, close_set_rate_asof_diff, avg_games_per_set_asof_diff

### fam: tennis_states
sport: tennis
horizon: live_tick
market: inplay
features: 5
hypotheses: 45
sources: data/cache/ingame/tennis_states__atp.parquet, data/cache/ingame/tennis_states__wta.parquet
members: asof_idx, state_diff, frac_elapsed, p0, outcome

### fam: tennis_travel_scouting
sport: tennis
horizon: pregame
market: ml
features: 3
hypotheses: 27
sources: data/domains/tennis/travel_scouting.parquet
members: is_p1, miles_flown_in, venue_altitude_m

