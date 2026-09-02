# S58 -- PROMOTION LIST from the first REAL screens (2026-09-03)

Calibration language only. Every number here is a SCREEN: a NON-FINDING on the SCREEN side of the
frozen partition. Nothing was charged (this lane wrote 0 ledger rows). The orchestrator releases T2
charges serially from this list later.

Module commit: 9235e9cb1 (`foundry/screen_predictor.py`, tiers T1, runner `--predictor real`,
`seed_queue --frozen`, `foundry/promotion_report.py`, test 3/3). Prereg pins embedded on every row:
FACTORY_TIERS_SPEC `b2b2ea5a0fe2bd4adaf327aa38e546b49ca0eec3` (top_n 20, group_by family,iso_week,
rank_by t1_brier_improvement, seed 20260903), FWER_FAMILIES_SPEC `62702554f6e57ec9f3182e8edc1e4d6a109a3b41`.

## PREMISE (Q8) -- HELD
The S16 runs used `_p_base_predict` (pass-through) as the T1 predictor, so every prior SCREEN measured
throughput, not content (S16 memo, NOT VERIFIED list). Re-read on disk before the change: the runner
had no predictor flag and `tiers.run_tier` T1 computed Brier only (no DM, no n_eff, no archive).

## INCIDENT found at lane start (not this lane's change; reported, restored)
At 10:32:11 local the working tree had 3,130 tracked files overwritten with STALE blobs (each byte-
identical to an older commit's version of the file: walkforward.py = pre-S40b, close_join.py =
pre-S48, foundry_runner.py = pre-S16, fwer_budget.py without `DEFAULT_Q`, so `from foundry import
tiers` failed repo-wide). Five files carried live edits with later stamps (results_db.py + its test,
nested_cv.py, artifact_refresh.py + its test) and were left untouched. The 3,130 were restored to
HEAD with `git checkout HEAD -- <list>` (list in this session's scratchpad, clobber_list.txt). The
signature is the stale-worktree `git archive <old sha> | tar -x` landing recipe applied to the whole
tree. Filed as a NEW GAP in the lane report.

## WHAT THE SCREEN IS
For hypothesis h = (sport, feature, transform, params) on gate corpus C:
- states: `corpus_states(sport)` -- soccer/tennis = `close_join.gate_corpus_states` (devigged close,
  SYNTHETIC 12:00 state_ts per S34); nba/mlb = `load_gate_corpus` + games.parquet teams, incumbent
  `p_base` (Elo) LABELLED. Partition per SF-1/SF-11: soccer by corpus_unit (5 divs: SCREEN = E0, F1),
  nba / mlb / tennis by ISO week (two-unit corpora). Screen window = last 800 SCREEN-side rows.
- feature: a gate-corpus column (as-of by construction) or a one-row-per-event `asof` join from the
  frozen family's own source parquets; a same-game / in-game column is refused BY NAME before any
  value is read (`LEAKY_NAMES` = S53's soccer list + the in-game state names, plus a same-game regex
  on non-asof names). Transforms use prior rows of the same cluster only (`shift(1)`), or the same-day
  cross-section of as-of values (rank / z vs league).
- model: `walk_forward` (purge 48h same-team, embargo 3d same matchup, vintage asserted per row),
  logistic on [1, logit(p_ref), z(feature)] refit every 50 train rows (each fit serves only later
  rows), ridge 1e-3, >= 30 fit rows else p_ref (missing != bad, B3).
- score: paired Brier delta (model - incumbent), cluster-robust DM p (team / div / player per SF-10),
  n_eff by ICC design effect; the per-unit differential (event_id, ts, cluster, loss_model,
  loss_incumbent) and every refit's coefficients are ARCHIVED in the trial JSON (Q9).

## RUN (local, four processes in parallel, one DB per sport)
Seeded with `seed_queue --frozen --sport <s>`: 3,564 enumerated over all 37 families -> 3,240 DISTINCT
semantic hashes (nba 1,332 / mlb 333 / soccer 531 / tennis 1,044; a member shared by two families with
the same sport/horizon/market collapses to one hash, e.g. nba_pbp_states is a subset of
nba_pbp_foul_states). DBs: `data/cache/eval_gate/s58_screens/<sport>.sqlite`; trial JSONs with the
archived differentials: `data/cache/eval_gate/s58_screens/trials_<sport>/<hash>_T1_all.json`
(nba 1,444 / mlb 138 / soccer 314 / tennis 1,201 files incl. T0). Logs `<sport>.log`, `<sport>.rerun.log`.
Reproduce the list: `python -m scripts.platformkit.foundry.promotion_report --db <the four sqlite paths>`.

Wall: started 2026-09-02T17:08:47Z, last exit 17:12:56Z = 249 s for all 3,240 claims (mlb 36 s,
soccer 76 s, tennis 249 s, nba 249 s). Then 36 `p_base` hypotheses (refused by the first name rule,
which excluded the spine's p_base; fixed to allow the base as a frozen *_gate member) were re-queued
and screened in about 10 s per sport. Throughput: 3,240 claims / 249 s = 46,800 claims/hour and
1,180 T1 screens / 249 s = 17,060 real screens/hour across 4 processes (about 4,300/hour/process;
the S16 fixture measured 10,320/hour on one process). The pod runner (pid 165812) was not used.

Real ledger `data/cache/eval_gate/backtest_fwer.jsonl`: 15 rows md5 b118ebd826026b7b9e59bdf89872ce16
at lane start; 17 rows md5 303a7d82cf525d338e258ef565c71d02 at the end -- the two rows are the OTHER
lane's (`s58_clamp_family_trial`, `s58_nba_halftime_asof_trial`). This lane's ledger paths
`s58_screens/fwer_<sport>_never_written.jsonl` do not exist (0 files). Charges by this lane: 0.

## HONEST DISTRIBUTION OF ALL 3,240 CLAIMS (denominator = every claimed hash, nothing dropped)

| sport | claimed | T1 SCREEN | T0 UNCOVERED (<80% non-null after join) | refused: leaky name | refused: unavailable | beat incumbent (delta<0) | beat RECALIBRATED incumbent |
|---|---|---|---|---|---|---|---|
| nba | 1,332 | 564 | 316 | 153 | 299 | 463 / 564 | 62 / 564 |
| mlb | 333 | 48 | 42 | 153 | 90 | 0 / 48 | 2 / 48 |
| soccer | 531 | 157 | 0 | 288 | 86 | 0 / 157 | 37 / 157 |
| tennis | 1,044 | 443 | 315 | 45 | 241 | 0 / 443 | 107 / 443 |
| total | 3,240 | 1,212 | 673 | 639 | 716 | 463 | 208 |

The RECALIBRATED incumbent is the same logistic with a constant (information-free) feature, computed
per sport on the same 800-row window (`s58_screens/null_reference.json`): nba p_base 0.205118 ->
0.203813 (recalibration alone improves Elo by -0.001305, so 463/564 NBA "beats" are mostly the
intercept/slope refit, NOT the feature -- only 62 beat the recalibrated base); mlb 0.249660 ->
0.253612 (+0.003953); soccer close 0.241896 -> 0.243801 (+0.001906); tennis close 0.197611 ->
0.200966 (+0.003355). Against a real devigged close, ZERO of 600 soccer+tennis screens beat the
close by any margin; the closest is soccer_gate `diff_sot_for_asof` at +0.000968. That is the
expected, honest picture (the market is efficient; a screen refits noise). NBA/MLB deltas are
against p_base = Elo, not a close, and must be read as such.

Refusals by family: every live_tick family (13; in-game state columns on a pregame corpus) = leaky by
name; player/pitcher/referee-grain families (nba_player_adv, nba_player_value_features,
nba_opp_allowed, mlb_bullpen_relief_chains, mlb_catcher_framing_index,
soccer_referee_card_foul_profiles, soccer_style_fingerprints (also S53-leaky), tennis_schedule_density,
tennis_serve_return_profiles, tennis_travel_scouting, tennis_meta, tennis_features, tennis_return)
= unavailable (>1 row per event, no asof name, or WTA sources whose event_ids never join the gate
spine); `ratio_to_opponent` on a `diff_*` column = unavailable (no twin). Of 37 frozen families 12
produced at least one SCREEN. 25 hypotheses are listed under two families (shared members), so the
report's 1,237 rows index 1,212 distinct screens.

Label mismatch to state: `mlb_inning` is frozen as (period, total) and `nba_quarter_shape` as
(period, spread), but this lane scored every family against the sport's pregame ML / over2.5 gate
corpus. Their SCREEN rows are on the wrong market and should NOT be charged from this list.
`mlb_gate` lists p_home_elo and p_base as separate hashes with identical deltas (same column).

## PROMOTION LIST (frozen rule: top 20 per family per ISO week by t1_brier_improvement)
Family recomputed from FWER_FAMILIES_SPEC by (sport, horizon, market, member) -- the DB `family`
column was not trusted (S66). 12 families x 20 = 240 candidates. Deltas are model minus incumbent
on the SCREEN partition (sha in the table); a negative delta is a SCREEN, not a finding. A T2 on
any of them reads the VERDICT side only (`ScreenPartitionLeak` otherwise), needs `screened_n`
(= the family's `screened` column below) and both bars (global deflated p at the launch K, family BH).

screens=1237 families=12 promoted=240 rule=v1 top_n=20 prereg=b2b2ea5a0fe2bd4adaf327aa38e546b49ca0eec3
distribution: {'delta<0': 470, 'delta>=0': 767}
| family | iso_week | screened | beat incumbent (delta<0) | promoted | best delta | best n_eff | incumbent | partition sha (screen) |
|---|---|---|---|---|---|---|---|---|
| mlb_gate | 2026-W36 | 24 | 0 | 20 | +0.002978 | 800.0 | p_base | ad743c924c7c4547 |
| mlb_inning | 2026-W36 | 24 | 0 | 20 | +0.004620 | 623.7 | p_base | ad743c924c7c4547 |
| nba_boxdetail | 2026-W36 | 250 | 211 | 20 | -0.002244 | 800.0 | p_base | 1a32541d44aa7fcb |
| nba_carryover | 2026-W36 | 50 | 40 | 20 | -0.001483 | 800.0 | p_base | 1a32541d44aa7fcb |
| nba_defender_rollup | 2026-W36 | 72 | 61 | 20 | -0.002747 | 711.4 | p_base | 1a32541d44aa7fcb |
| nba_gate | 2026-W36 | 88 | 80 | 20 | -0.002755 | 800.0 | p_base | 1a32541d44aa7fcb |
| nba_team_adv | 2026-W36 | 112 | 78 | 20 | -0.002181 | 752.5 | p_base | 1a32541d44aa7fcb |
| soccer_gate | 2026-W36 | 82 | 0 | 20 | +0.000968 | 667.8 | devig_close | 5c8d63970b08ce97 |
| soccer_xg_proxy | 2026-W36 | 75 | 0 | 20 | +0.001445 | 382.4 | devig_close | 5c8d63970b08ce97 |
| tennis_gate | 2026-W36 | 33 | 0 | 20 | +0.003347 | 709.0 | devig_close | c8dde4f3a44c8e58 |
| tennis_hold | 2026-W36 | 134 | 0 | 20 | +0.001743 | 397.1 | devig_close | c8dde4f3a44c8e58 |
| tennis_setdetail | 2026-W36 | 293 | 0 | 20 | +0.000877 | 736.1 | devig_close | c8dde4f3a44c8e58 |

## Candidates per family (SCREEN deltas -- NOT findings)

### mlb_gate (2026-W36)
| rank | feature | transform | params | delta (model - incumbent) | screen DM p | n | n_eff | hash |
|---|---|---|---|---|---|---|---|---|
| 1 | p_home_elo | rank_in_league | - | +0.002978 | 0.1697 | 800 | 800.0 | 20ec4b89eb68fba0 |
| 2 | p_base | rank_in_league | - | +0.002978 | 0.1697 | 800 | 800.0 | 3daf4b893fe3715f |
| 3 | p_home_elo | raw | - | +0.004067 | 0.0476 | 800 | 800.0 | 1a5c2af36be83005 |
| 4 | p_base | raw | - | +0.004067 | 0.0476 | 800 | 800.0 | 5204ddf10a3f2039 |
| 5 | p_home_elo | z_vs_league | - | +0.004075 | 0.0465 | 800 | 800.0 | 00fe9b94e5434470 |
| 6 | p_base | z_vs_league | - | +0.004075 | 0.0465 | 800 | 800.0 | 09e038facbd1be62 |
| 7 | p_home_elo | delta_vs_prior | - | +0.004258 | 0.0398 | 800 | 800.0 | 857216efce16b2f7 |
| 8 | p_base | delta_vs_prior | - | +0.004258 | 0.0398 | 800 | 800.0 | ac62facb7790f0df |
| 9 | p_base | ew | {'halflife': 3} | +0.005358 | 0.0224 | 800 | 708.2 | 1af403180ab37ce6 |
| 10 | p_home_elo | ew | {'halflife': 3} | +0.005358 | 0.0224 | 800 | 708.2 | dcf0554d2e0d6dac |
| 11 | sp_ra_diff_asof | ew | {'halflife': 5} | +0.005641 | 0.0299 | 800 | 754.6 | 1a168ef7365ab164 |
| 12 | sp_ra_diff_asof | ew | {'halflife': 3} | +0.005689 | 0.0314 | 800 | 767.4 | efdc25b6beac0e4c |
| 13 | sp_first6_diff_ew | ew | {'halflife': 20} | +0.005696 | 0.0114 | 800 | 800.0 | df1dddd9abd8f68e |
| 14 | sp_ra_diff_asof | ew | {'halflife': 10} | +0.005705 | 0.0327 | 800 | 684.6 | 9f82bd0c731a8c1d |
| 15 | sp_first6_diff_ew | ew | {'halflife': 10} | +0.005793 | 0.0049 | 800 | 800.0 | d86695abd3c42465 |
| 16 | p_home_elo | ew | {'halflife': 5} | +0.005804 | 0.0185 | 800 | 735.5 | 62d11c015bf7bf07 |
| 17 | p_base | ew | {'halflife': 5} | +0.005804 | 0.0185 | 800 | 735.5 | 6b957d3d3bd61ec7 |
| 18 | sp_ra_diff_asof | ew | {'halflife': 20} | +0.005982 | 0.0322 | 800 | 639.7 | c292b9a3a7b691ef |
| 19 | sp_first6_diff_ew | ew | {'halflife': 3} | +0.006008 | 0.0041 | 800 | 800.0 | dec49e90dcf11d03 |
| 20 | p_home_elo | ew | {'halflife': 10} | +0.006210 | 0.0154 | 800 | 790.5 | c91ad7ccc0321cb6 |

### mlb_inning (2026-W36)
| rank | feature | transform | params | delta (model - incumbent) | screen DM p | n | n_eff | hash |
|---|---|---|---|---|---|---|---|---|
| 1 | away_late_rate_asof | ew | {'halflife': 3} | +0.004620 | 0.0430 | 800 | 623.7 | a85747a0b2df203e |
| 2 | home_late_rate_asof | ew | {'halflife': 20} | +0.004774 | 0.0176 | 800 | 800.0 | bd059ef00bc8a799 |
| 3 | late_rate_diff_asof | ew | {'halflife': 3} | +0.004787 | 0.0186 | 800 | 800.0 | f439aa39182d629c |
| 4 | home_late_rate_asof | ew | {'halflife': 10} | +0.004819 | 0.0169 | 800 | 800.0 | 0bfe9fb65a148665 |
| 5 | away_late_rate_asof | ew | {'halflife': 5} | +0.004826 | 0.0495 | 800 | 587.4 | 884f0440812b002b |
| 6 | home_late_rate_asof | ew | {'halflife': 5} | +0.004853 | 0.0163 | 800 | 800.0 | adea1120de50954e |
| 7 | home_late_rate_asof | ew | {'halflife': 3} | +0.004865 | 0.0161 | 800 | 800.0 | dbfea0d2aed24488 |
| 8 | late_rate_diff_asof | ew | {'halflife': 20} | +0.004870 | 0.0205 | 800 | 800.0 | 160ea3c50739500f |
| 9 | home_early_rate_asof | ew | {'halflife': 20} | +0.004905 | 0.0230 | 800 | 800.0 | 25fe5e21051e3686 |
| 10 | home_early_rate_asof | ew | {'halflife': 10} | +0.004920 | 0.0221 | 800 | 800.0 | 4e06fff06c82e4ea |
| 11 | home_early_rate_asof | ew | {'halflife': 5} | +0.004940 | 0.0214 | 800 | 800.0 | 128ff5c82264d2d8 |
| 12 | late_rate_diff_asof | ew | {'halflife': 5} | +0.004943 | 0.0178 | 800 | 800.0 | d5126c1ed5da79fd |
| 13 | home_early_rate_asof | ew | {'halflife': 3} | +0.004949 | 0.0211 | 800 | 800.0 | ee6cf23c61f0aede |
| 14 | late_rate_diff_asof | ew | {'halflife': 10} | +0.004988 | 0.0190 | 800 | 800.0 | cf2842b7641987d1 |
| 15 | away_late_rate_asof | ew | {'halflife': 20} | +0.005087 | 0.0392 | 800 | 754.3 | a370e1bb19843a8c |
| 16 | away_early_rate_asof | ew | {'halflife': 20} | +0.005108 | 0.0134 | 800 | 800.0 | bef6ba2cb5500a9d |
| 17 | away_late_rate_asof | ew | {'halflife': 10} | +0.005180 | 0.0477 | 800 | 634.5 | ecc30b2ba1a49836 |
| 18 | early_rate_diff_asof | ew | {'halflife': 3} | +0.005240 | 0.0116 | 800 | 800.0 | 532881ea9727c42e |
| 19 | early_rate_diff_asof | ew | {'halflife': 5} | +0.005253 | 0.0123 | 800 | 800.0 | 5ede525ea2413f62 |
| 20 | early_rate_diff_asof | ew | {'halflife': 10} | +0.005274 | 0.0143 | 800 | 800.0 | 73105f6b71f28ad8 |

### nba_boxdetail (2026-W36)
| rank | feature | transform | params | delta (model - incumbent) | screen DM p | n | n_eff | hash |
|---|---|---|---|---|---|---|---|---|
| 1 | tov_pts_l10_diff_asof | rank_in_league | - | -0.002244 | 0.4099 | 800 | 800.0 | 75bc85c39cc53243 |
| 2 | home_tov_pts_l10_asof | ratio_to_opponent | - | -0.002127 | 0.3365 | 800 | 800.0 | 65c43fad6046cac4 |
| 3 | away_tov_pts_l10_asof | rank_in_league | - | -0.002076 | 0.3911 | 800 | 800.0 | 5f50fa446c0a8ff0 |
| 4 | away_foul_trouble_asof | ew | {'halflife': 20} | -0.001981 | 0.3261 | 800 | 747.6 | d1d1c60852c247b3 |
| 5 | away_foul_trouble_asof | ew | {'halflife': 10} | -0.001939 | 0.3334 | 800 | 752.8 | ea2be906b2024606 |
| 6 | largest_lead_l10_diff_asof | delta_vs_prior | - | -0.001838 | 0.3638 | 800 | 800.0 | 089f78dd78bc1f6b |
| 7 | away_foul_trouble_asof | ew | {'halflife': 5} | -0.001736 | 0.3877 | 800 | 751.2 | 8ce3a878f00c110c |
| 8 | away_largest_lead_l10_asof | delta_vs_prior | - | -0.001692 | 0.4010 | 800 | 800.0 | 6987c975abb3d968 |
| 9 | tov_pts_l10_diff_asof | delta_vs_prior | - | -0.001664 | 0.3961 | 800 | 800.0 | bbbadc7ac47c8403 |
| 10 | tov_pts_l10_diff_asof | raw | - | -0.001642 | 0.4633 | 800 | 800.0 | 2889c3ef65daa8c5 |
| 11 | away_foul_trouble_l10_asof | rank_in_league | - | -0.001633 | 0.4712 | 800 | 740.1 | 5fdb9667c93ed96f |
| 12 | away_tov_pts_l10_asof | delta_vs_prior | - | -0.001576 | 0.4600 | 800 | 800.0 | b658e1b520ff12c9 |
| 13 | away_foul_trouble_asof | ew | {'halflife': 3} | -0.001439 | 0.4806 | 800 | 738.0 | f34e19fe3eab8563 |
| 14 | away_paint_pts_l10_asof | rank_in_league | - | -0.001413 | 0.5325 | 800 | 800.0 | 4a3698a8eb644299 |
| 15 | tov_pts_l10_diff_asof | z_vs_league | - | -0.001378 | 0.5588 | 800 | 800.0 | 1015a03637b6d94d |
| 16 | away_foul_trouble_l10_asof | raw | - | -0.001360 | 0.5719 | 800 | 798.0 | e5b99abbee35a993 |
| 17 | away_foul_trouble_l10_asof | ew | {'halflife': 20} | -0.001336 | 0.5226 | 800 | 719.6 | ada4d793dc198955 |
| 18 | away_fast_break_pts_l10_asof | raw | - | -0.001323 | 0.5511 | 800 | 788.5 | f89c63188c22bd52 |
| 19 | away_tov_pts_l10_asof | raw | - | -0.001315 | 0.5035 | 800 | 800.0 | 509798d0b453922d |
| 20 | home_foul_trouble_asof | ew | {'halflife': 20} | -0.001289 | 0.5111 | 800 | 797.3 | 7d75d156b954b256 |

### nba_carryover (2026-W36)
| rank | feature | transform | params | delta (model - incumbent) | screen DM p | n | n_eff | hash |
|---|---|---|---|---|---|---|---|---|
| 1 | away_heavy_min_load_asof | ew | {'halflife': 20} | -0.001483 | 0.4242 | 800 | 800.0 | 9e22c0e945d12195 |
| 2 | away_heavy_min_load_asof | ew | {'halflife': 10} | -0.001308 | 0.4819 | 800 | 800.0 | 553692d75b372fb8 |
| 3 | rest_days_diff_asof | rank_in_league | - | -0.001175 | 0.5360 | 800 | 800.0 | 614dbcec04ec3996 |
| 4 | away_rest_days_asof | delta_vs_prior | - | -0.001169 | 0.5578 | 800 | 800.0 | 7234f8d1a901bd55 |
| 5 | home_rest_days_asof | rank_in_league | - | -0.001024 | 0.6685 | 800 | 705.4 | 7b569581564ce7d8 |
| 6 | away_heavy_min_load_asof | ew | {'halflife': 5} | -0.001010 | 0.5926 | 800 | 800.0 | 9aa16123efcb981d |
| 7 | away_rest_days_asof | z_vs_league | - | -0.000949 | 0.6069 | 800 | 800.0 | 1de0dc2062272a4d |
| 8 | away_heavy_min_load_asof | raw | - | -0.000946 | 0.5810 | 800 | 800.0 | ccf5d710846f9d4f |
| 9 | away_rest_days_asof | ew | {'halflife': 20} | -0.000923 | 0.6345 | 800 | 800.0 | 77d25d53afb16a84 |
| 10 | rest_days_diff_asof | delta_vs_prior | - | -0.000916 | 0.6830 | 800 | 773.8 | 1ed673e42c291360 |
| 11 | away_heavy_min_load_asof | z_vs_league | - | -0.000907 | 0.5995 | 800 | 800.0 | e91cc8dcd1acd223 |
| 12 | heavy_min_load_diff_asof | ew | {'halflife': 20} | -0.000905 | 0.6641 | 800 | 777.3 | ffa3675665240aaa |
| 13 | away_rest_days_asof | ew | {'halflife': 10} | -0.000892 | 0.6480 | 800 | 800.0 | ee487322019bf542 |
| 14 | away_rest_days_asof | ew | {'halflife': 5} | -0.000828 | 0.6757 | 800 | 800.0 | 889f53ee0f2f7f58 |
| 15 | rest_days_diff_asof | ew | {'halflife': 20} | -0.000817 | 0.6894 | 800 | 760.1 | e7fa27b1950cfa4a |
| 16 | rest_days_diff_asof | ew | {'halflife': 10} | -0.000813 | 0.6937 | 800 | 747.2 | a4a76e29a1add6fe |
| 17 | rest_days_diff_asof | ew | {'halflife': 5} | -0.000811 | 0.6969 | 800 | 738.1 | ef61a0ead6b3bbb8 |
| 18 | away_rest_days_asof | raw | - | -0.000807 | 0.6607 | 800 | 800.0 | 75b91732d4f6233f |
| 19 | away_heavy_min_load_asof | ew | {'halflife': 3} | -0.000789 | 0.6865 | 800 | 800.0 | 397543b58671b404 |
| 20 | rest_days_diff_asof | ew | {'halflife': 3} | -0.000780 | 0.7065 | 800 | 749.9 | 45be24ea41dfdaf9 |

### nba_defender_rollup (2026-W36)
| rank | feature | transform | params | delta (model - incumbent) | screen DM p | n | n_eff | hash |
|---|---|---|---|---|---|---|---|---|
| 1 | def_matchup_min_diff_asof | ew | {'halflife': 20} | -0.002747 | 0.2930 | 800 | 711.4 | 5944a638d903abef |
| 2 | def_matchup_min_diff_asof | ew | {'halflife': 10} | -0.002635 | 0.3042 | 800 | 737.9 | 7b95384d2d294162 |
| 3 | def_matchup_min_diff_asof | ew | {'halflife': 5} | -0.002477 | 0.3252 | 800 | 776.3 | c7cd05d2db302050 |
| 4 | def_matchup_min_diff_asof | ew | {'halflife': 3} | -0.002400 | 0.3418 | 800 | 794.6 | aa218e80ebc52201 |
| 5 | away_def_matchup_min_asof | ew | {'halflife': 20} | -0.001862 | 0.3432 | 800 | 800.0 | a1406ff90b0572cd |
| 6 | away_def_matchup_min_asof | ew | {'halflife': 10} | -0.001690 | 0.3756 | 800 | 800.0 | 7764c709c94c46dd |
| 7 | away_def_matchup_min_asof | ew | {'halflife': 5} | -0.001404 | 0.4392 | 800 | 800.0 | 7c2d9c18e4789296 |
| 8 | def_switches_per_game_diff_asof | ew | {'halflife': 20} | -0.001345 | 0.4863 | 800 | 800.0 | 16e36d3abc1df896 |
| 9 | away_def_switches_per_game_asof | ew | {'halflife': 10} | -0.001345 | 0.4863 | 800 | 800.0 | 1745a69cd0486f99 |
| 10 | home_def_switches_per_game_asof | ew | {'halflife': 20} | -0.001345 | 0.4863 | 800 | 800.0 | 339f7fbc915561a1 |
| 11 | def_switches_per_game_diff_asof | ew | {'halflife': 5} | -0.001345 | 0.4863 | 800 | 800.0 | 7a0dae56783c5f47 |
| 12 | away_def_switches_per_game_asof | ew | {'halflife': 3} | -0.001345 | 0.4863 | 800 | 800.0 | 80e5833e4d660cc2 |
| 13 | home_def_switches_per_game_asof | ew | {'halflife': 5} | -0.001345 | 0.4863 | 800 | 800.0 | 80fdc00d0337e89e |
| 14 | home_def_switches_per_game_asof | ew | {'halflife': 3} | -0.001345 | 0.4863 | 800 | 800.0 | 84051d3311bec811 |
| 15 | away_def_switches_per_game_asof | ew | {'halflife': 20} | -0.001345 | 0.4863 | 800 | 800.0 | 8aaaf5d7f688111a |
| 16 | def_switches_per_game_diff_asof | ew | {'halflife': 10} | -0.001345 | 0.4863 | 800 | 800.0 | c9a275fffa9a2a29 |
| 17 | away_def_switches_per_game_asof | ew | {'halflife': 5} | -0.001345 | 0.4863 | 800 | 800.0 | eef3ddf45a3b3cdd |
| 18 | def_switches_per_game_diff_asof | ew | {'halflife': 3} | -0.001345 | 0.4863 | 800 | 800.0 | f26c3f9370440a01 |
| 19 | home_def_switches_per_game_asof | ew | {'halflife': 10} | -0.001345 | 0.4863 | 800 | 800.0 | fb0df6e57a879657 |
| 20 | away_def_matchup_min_asof | ew | {'halflife': 3} | -0.001196 | 0.4907 | 800 | 800.0 | bdcbbc178f83f2a7 |

### nba_gate (2026-W36)
| rank | feature | transform | params | delta (model - incumbent) | screen DM p | n | n_eff | hash |
|---|---|---|---|---|---|---|---|---|
| 1 | dreb_x_pace_asof | ew | {'halflife': 3} | -0.002755 | 0.2302 | 800 | 800.0 | 4887b12a4a6a1518 |
| 2 | dreb_x_pace_asof | ew | {'halflife': 5} | -0.002635 | 0.2435 | 800 | 800.0 | 66fb129565d9609b |
| 3 | dreb_x_pace_asof | ew | {'halflife': 10} | -0.002539 | 0.2564 | 800 | 800.0 | 00b405d3264df583 |
| 4 | dreb_x_pace_asof | ew | {'halflife': 20} | -0.002478 | 0.2669 | 800 | 800.0 | 97bcc465b2653ecf |
| 5 | p_elo | rank_in_league | - | -0.001498 | 0.4338 | 800 | 800.0 | 9bc13ba5acd26bb5 |
| 6 | p_base | rank_in_league | - | -0.001498 | 0.4338 | 800 | 800.0 | e92bff05c7260548 |
| 7 | stl_x_fg3m_asof | delta_vs_prior | - | -0.001443 | 0.4318 | 800 | 800.0 | 347c835e4fb80986 |
| 8 | dreb_x_pace_asof | delta_vs_prior | - | -0.001395 | 0.5048 | 800 | 800.0 | 45d0bf3c193d9fd8 |
| 9 | fg3m_diff_asof | ew | {'halflife': 3} | -0.001379 | 0.4285 | 800 | 800.0 | 1d62556555b8c0c9 |
| 10 | fg3m_diff_asof | ew | {'halflife': 5} | -0.001374 | 0.4282 | 800 | 800.0 | e6f607cc3af05ffe |
| 11 | fg3m_diff_asof | ew | {'halflife': 10} | -0.001360 | 0.4309 | 800 | 800.0 | 670d823c50d8ac7c |
| 12 | oreb_pg_diff_asof | delta_vs_prior | - | -0.001357 | 0.5048 | 800 | 800.0 | 8b012e942acd5e02 |
| 13 | fg3m_diff_asof | ew | {'halflife': 20} | -0.001345 | 0.4350 | 800 | 800.0 | 0a40fe4df45cd7fe |
| 14 | dreb_diff_asof | delta_vs_prior | - | -0.001165 | 0.5170 | 800 | 800.0 | f0c8e903d8c7ea37 |
| 15 | oreb_pg_diff_asof | raw | - | -0.001138 | 0.5722 | 800 | 746.6 | c330144137a55af6 |
| 16 | blk_diff_asof | ew | {'halflife': 20} | -0.001133 | 0.5635 | 800 | 782.5 | 05aa48bf148197df |
| 17 | oreb_pg_diff_asof | z_vs_league | - | -0.001122 | 0.5989 | 800 | 726.6 | d70f0b3ffd86f736 |
| 18 | blk_diff_asof | ew | {'halflife': 10} | -0.001114 | 0.5721 | 800 | 774.2 | c98205a50874ee3a |
| 19 | blk_diff_asof | ew | {'halflife': 5} | -0.001091 | 0.5839 | 800 | 759.8 | c51746431e590a61 |
| 20 | dreb_x_pace_asof | rank_in_league | - | -0.001088 | 0.5996 | 800 | 792.6 | 706e2da6eb885333 |

### nba_team_adv (2026-W36)
| rank | feature | transform | params | delta (model - incumbent) | screen DM p | n | n_eff | hash |
|---|---|---|---|---|---|---|---|---|
| 1 | away_ts_pct_asof | ew | {'halflife': 3} | -0.002181 | 0.3569 | 800 | 752.5 | 59a6551049bf12a3 |
| 2 | away_ts_pct_asof | ew | {'halflife': 5} | -0.002030 | 0.3738 | 800 | 790.7 | cfe52a0e983ba830 |
| 3 | away_ts_pct_asof | ew | {'halflife': 10} | -0.001873 | 0.3977 | 800 | 800.0 | d92882a7e0c27175 |
| 4 | away_efg_pct_asof | ew | {'halflife': 3} | -0.001821 | 0.4212 | 800 | 768.2 | 448d4db237458d1a |
| 5 | away_ts_pct_asof | ew | {'halflife': 20} | -0.001793 | 0.4111 | 800 | 800.0 | 7aa6ef5302076adb |
| 6 | away_efg_pct_asof | ew | {'halflife': 5} | -0.001723 | 0.4334 | 800 | 800.0 | 4577a914796b4c25 |
| 7 | away_efg_pct_asof | ew | {'halflife': 10} | -0.001618 | 0.4514 | 800 | 800.0 | 3f4566d151a4184e |
| 8 | away_efg_pct_asof | ew | {'halflife': 20} | -0.001563 | 0.4619 | 800 | 800.0 | 0b15be4474550656 |
| 9 | away_oreb_pct_asof | ew | {'halflife': 3} | -0.001321 | 0.5999 | 800 | 769.2 | 65ae78b15846ac48 |
| 10 | away_oreb_pct_asof | ew | {'halflife': 5} | -0.001223 | 0.6188 | 800 | 779.8 | b659aab214f8a3b4 |
| 11 | away_off_rtg_asof | ew | {'halflife': 20} | -0.001209 | 0.5416 | 800 | 798.8 | 60f0899b4c49c0d3 |
| 12 | away_off_rtg_asof | ew | {'halflife': 10} | -0.001187 | 0.5524 | 800 | 790.9 | 9bfca9ff491cd01b |
| 13 | away_off_rtg_asof | ew | {'halflife': 5} | -0.001142 | 0.5750 | 800 | 773.4 | 89840415012ec5dc |
| 14 | away_tov_ratio_asof | ew | {'halflife': 20} | -0.001087 | 0.5795 | 800 | 800.0 | cebd70841f401ee0 |
| 15 | away_off_rtg_asof | ew | {'halflife': 3} | -0.001079 | 0.6046 | 800 | 752.4 | 128abb91aa856e70 |
| 16 | away_tov_ratio_asof | ew | {'halflife': 10} | -0.001078 | 0.5845 | 800 | 800.0 | 90cccadf653e6d7d |
| 17 | away_tov_ratio_asof | ew | {'halflife': 5} | -0.001056 | 0.5960 | 800 | 800.0 | 6fdec96f8bad3a9b |
| 18 | away_oreb_pct_asof | ew | {'halflife': 10} | -0.001054 | 0.6618 | 800 | 783.3 | 00e76aca3af3a881 |
| 19 | away_pace_asof | ew | {'halflife': 20} | -0.001049 | 0.5725 | 800 | 800.0 | a6595a8a1d6743f6 |
| 20 | away_tov_ratio_asof | ew | {'halflife': 3} | -0.001025 | 0.6127 | 800 | 793.8 | 6f115b9bf1494892 |

### soccer_gate (2026-W36)
| rank | feature | transform | params | delta (model - incumbent) | screen DM p | n | n_eff | hash |
|---|---|---|---|---|---|---|---|---|
| 1 | diff_shots_for_asof | ew | {'halflife': 10} | +0.000968 | 0.7175 | 800 | 667.8 | d65df2a95aeb0f49 |
| 2 | away_sot_for_l10 | ew | {'halflife': 10} | +0.001070 | 0.5768 | 800 | 800.0 | 51296c9afdd73f30 |
| 3 | diff_shots_for_asof | ew | {'halflife': 20} | +0.001084 | 0.6556 | 800 | 769.9 | 79b6009d1e145fd6 |
| 4 | diff_shots_for_asof | ew | {'halflife': 5} | +0.001238 | 0.6921 | 800 | 546.4 | 139822e9250d04b4 |
| 5 | away_sot_for_l10 | ew | {'halflife': 5} | +0.001248 | 0.6541 | 800 | 472.9 | 2ad92ea5dda8f194 |
| 6 | diff_shots_for_asof | ew | {'halflife': 3} | +0.001265 | 0.7073 | 800 | 497.2 | 34b474d8ec14f1e2 |
| 7 | away_sot_for_l10 | ew | {'halflife': 3} | +0.001347 | 0.7089 | 800 | 310.3 | 2d6e4f8753a0d0cf |
| 8 | away_sot_for_l10 | ew | {'halflife': 20} | +0.001402 | 0.3806 | 800 | 800.0 | c39d671948a55af6 |
| 9 | p_over25 | ew | {'halflife': 20} | +0.001511 | 0.4891 | 800 | 625.6 | 28160a624c8fed9d |
| 10 | p_base | ew | {'halflife': 20} | +0.001511 | 0.4891 | 800 | 625.6 | a0b5debe22a7a3ab |
| 11 | diff_sot_against_asof | ew | {'halflife': 3} | +0.001535 | 0.6430 | 800 | 372.4 | 3c61545b92502c14 |
| 12 | diff_sot_for_asof | ew | {'halflife': 10} | +0.001537 | 0.5555 | 800 | 492.9 | 4ba2522a080db757 |
| 13 | p_base | ew | {'halflife': 3} | +0.001585 | 0.5725 | 800 | 366.4 | 41c2d6237e67a7aa |
| 14 | p_over25 | ew | {'halflife': 3} | +0.001585 | 0.5725 | 800 | 366.4 | bc1ac7d94582b43b |
| 15 | diff_sot_for_asof | ew | {'halflife': 20} | +0.001613 | 0.5019 | 800 | 534.6 | 5982fffa5d790501 |
| 16 | diff_sot_for_asof | ew | {'halflife': 3} | +0.001711 | 0.6086 | 800 | 376.4 | cad5f5333038d719 |
| 17 | diff_sot_for_asof | ew | {'halflife': 5} | +0.001713 | 0.5728 | 800 | 403.3 | 36a90200813cbedf |
| 18 | p_base | raw | - | +0.001723 | 0.6009 | 800 | 447.6 | 3ab940a0475f2d3a |
| 19 | p_over25 | raw | - | +0.001723 | 0.6009 | 800 | 447.6 | 5503f9b25c02c1e6 |
| 20 | p_over25 | z_vs_league | - | +0.001724 | 0.6012 | 800 | 447.9 | 0440b673881c1b3c |

### soccer_xg_proxy (2026-W36)
| rank | feature | transform | params | delta (model - incumbent) | screen DM p | n | n_eff | hash |
|---|---|---|---|---|---|---|---|---|
| 1 | diff_xg_supremacy_asof | ew | {'halflife': 3} | +0.001445 | 0.6798 | 800 | 382.4 | 5badbb3357bbde57 |
| 2 | diff_xg_for_asof | ew | {'halflife': 10} | +0.001445 | 0.5844 | 800 | 513.9 | bbf125b134d7a090 |
| 3 | diff_xg_supremacy_asof | ew | {'halflife': 10} | +0.001491 | 0.6080 | 800 | 475.5 | 9c44f3c7b3dec92d |
| 4 | diff_xg_for_asof | ew | {'halflife': 20} | +0.001531 | 0.5283 | 800 | 564.0 | 8792b166bdfb9889 |
| 5 | diff_xg_against_asof | ew | {'halflife': 3} | +0.001563 | 0.6362 | 800 | 377.9 | 2468682e2bde8434 |
| 6 | diff_xg_supremacy_asof | ew | {'halflife': 5} | +0.001570 | 0.6357 | 800 | 414.8 | 9df0ad02006282a3 |
| 7 | diff_xg_supremacy_asof | ew | {'halflife': 20} | +0.001588 | 0.5444 | 800 | 488.5 | e34f44d09ecf7935 |
| 8 | diff_xg_for_asof | ew | {'halflife': 5} | +0.001634 | 0.5962 | 800 | 419.3 | cc81f9bb8673512f |
| 9 | diff_xg_for_asof | ew | {'halflife': 3} | +0.001637 | 0.6284 | 800 | 389.8 | 9c57e2c1bc47ae4c |
| 10 | diff_xg_against_asof | ew | {'halflife': 5} | +0.001902 | 0.5750 | 800 | 404.6 | a4cf98eb16cc0be7 |
| 11 | diff_xg_against_asof | ew | {'halflife': 10} | +0.002027 | 0.5071 | 800 | 468.6 | e3821eadb24802fb |
| 12 | home_xg_supremacy_asof | ratio_to_opponent | - | +0.002066 | 0.2534 | 800 | 492.8 | 030d1f75a99fb061 |
| 13 | diff_xg_against_asof | ew | {'halflife': 20} | +0.002099 | 0.4336 | 800 | 494.7 | 5ad0893e78ffd8fe |
| 14 | away_xg_against_asof | ew | {'halflife': 5} | +0.002208 | 0.5463 | 800 | 162.0 | 0f633ffe5e122952 |
| 15 | away_xg_against_asof | ew | {'halflife': 10} | +0.002215 | 0.3621 | 800 | 338.9 | bf810b40dd36f069 |
| 16 | away_xg_supremacy_asof | ew | {'halflife': 3} | +0.002238 | 0.4799 | 800 | 280.7 | 630257bc498607a9 |
| 17 | away_xg_for_asof | ew | {'halflife': 3} | +0.002304 | 0.3183 | 800 | 585.9 | 91ea61a46ce415f4 |
| 18 | away_xg_supremacy_asof | ew | {'halflife': 5} | +0.002324 | 0.2831 | 800 | 592.0 | ff73095dba4bdab9 |
| 19 | home_xg_for_asof | delta_vs_prior | - | +0.002414 | 0.2592 | 800 | 321.4 | cef5ab9a6adfe838 |
| 20 | away_xg_against_asof | ew | {'halflife': 20} | +0.002464 | 0.1293 | 800 | 800.0 | b1e8e5612a05d299 |

### tennis_gate (2026-W36)
| rank | feature | transform | params | delta (model - incumbent) | screen DM p | n | n_eff | hash |
|---|---|---|---|---|---|---|---|---|
| 1 | p_base | z_vs_league | - | +0.003347 | 0.0152 | 800 | 709.0 | 012d4a74b9ff7b4b |
| 2 | p_elo | z_vs_league | - | +0.003347 | 0.0152 | 800 | 709.0 | 3b719d893601efc2 |
| 3 | p_elo | raw | - | +0.003350 | 0.0151 | 800 | 709.0 | 2b7ce0b1b297a5b3 |
| 4 | p_base | raw | - | +0.003350 | 0.0151 | 800 | 709.0 | 3f63d9f8b4586b08 |
| 5 | p1_hold_pct_asof | delta_vs_prior | - | +0.003372 | 0.3126 | 800 | 372.1 | d52ac6bbf28a101e |
| 6 | p_elo | rank_in_league | - | +0.003534 | 0.0155 | 800 | 719.5 | 42d2cb99d9d49119 |
| 7 | p_base | rank_in_league | - | +0.003534 | 0.0155 | 800 | 719.5 | 4b4b82187334c667 |
| 8 | p2_hold_pct_asof | ew | {'halflife': 20} | +0.003645 | 0.0433 | 800 | 754.2 | 6390382e41dfabab |
| 9 | p2_hold_pct_asof | ew | {'halflife': 10} | +0.003894 | 0.0536 | 800 | 766.0 | ad525d487bfe0774 |
| 10 | p2_hold_pct_asof | rank_in_league | - | +0.003992 | 0.0124 | 800 | 720.1 | 26f4489ccde75c75 |
| 11 | p2_hold_pct_asof | ew | {'halflife': 5} | +0.004061 | 0.0430 | 800 | 789.2 | 29631b0dbd9cbe35 |
| 12 | p2_hold_pct_asof | ew | {'halflife': 3} | +0.004094 | 0.0280 | 800 | 799.5 | 1685045cf0079c97 |
| 13 | p1_hold_pct_asof | rank_in_league | - | +0.004386 | 0.0079 | 800 | 726.1 | 0674cefc8c13a9da |
| 14 | p1_hold_pct_asof | ew | {'halflife': 3} | +0.004454 | 0.0014 | 800 | 777.3 | 22bb503289d41859 |
| 15 | p1_hold_pct_asof | ew | {'halflife': 5} | +0.004505 | 0.0012 | 800 | 800.0 | 3c3f2a22223ed17e |
| 16 | p1_hold_pct_asof | ew | {'halflife': 10} | +0.004532 | 0.0012 | 800 | 800.0 | 77bee2f91a57ac7e |
| 17 | p1_hold_pct_asof | ew | {'halflife': 20} | +0.004541 | 0.0011 | 800 | 800.0 | 119b8e7b4d5deb17 |
| 18 | p1_hold_pct_asof | ratio_to_opponent | - | +0.004742 | 0.0073 | 800 | 800.0 | f9eb1002da7ffe67 |
| 19 | p_elo | ew | {'halflife': 20} | +0.004769 | 0.0067 | 800 | 649.6 | 513a56ad72876d5d |
| 20 | p_base | ew | {'halflife': 20} | +0.004769 | 0.0067 | 800 | 649.6 | 7b25757f99d4138c |

### tennis_hold (2026-W36)
| rank | feature | transform | params | delta (model - incumbent) | screen DM p | n | n_eff | hash |
|---|---|---|---|---|---|---|---|---|
| 1 | p1_svpts_won_asof | delta_vs_prior | - | +0.001743 | 0.4601 | 800 | 397.1 | 23370e206f2ce534 |
| 2 | p2_svpts_won_grass_asof | z_vs_league | - | +0.002184 | 0.1679 | 800 | 774.4 | 270b87297681e6fa |
| 3 | p2_svpts_won_grass_asof | raw | - | +0.002192 | 0.1670 | 800 | 774.4 | d58243fb9939b291 |
| 4 | p2_hold_pct_grass_asof | z_vs_league | - | +0.002336 | 0.1118 | 800 | 789.4 | e0e0bd1010f63cb7 |
| 5 | p2_hold_pct_grass_asof | raw | - | +0.002343 | 0.1112 | 800 | 789.2 | afa809d5181f1b63 |
| 6 | p1_svpts_won_grass_asof | delta_vs_prior | - | +0.002493 | 0.0794 | 800 | 659.4 | 06ef4d3f5e53932c |
| 7 | p1_svpts_won_clay_asof | ratio_to_opponent | - | +0.002551 | 0.0698 | 800 | 761.9 | 25cf4c3a63480679 |
| 8 | p2_svpts_won_clay_asof | rank_in_league | - | +0.002575 | 0.0478 | 800 | 775.4 | 3ddc9c7f94866d78 |
| 9 | p2_svpts_won_clay_asof | ew | {'halflife': 20} | +0.002579 | 0.0320 | 800 | 800.0 | 84fcaea78eeb9961 |
| 10 | p1_hold_pct_grass_asof | delta_vs_prior | - | +0.002625 | 0.0536 | 800 | 773.1 | 53ec244bdf0c72ab |
| 11 | p2_svpts_won_clay_asof | ew | {'halflife': 10} | +0.002674 | 0.0300 | 800 | 800.0 | d81d04e385182cad |
| 12 | p2_hold_pct_clay_asof | rank_in_league | - | +0.002680 | 0.0441 | 800 | 753.3 | 962e2f4d8683ddce |
| 13 | p1_svpts_won_grass_asof | ratio_to_opponent | - | +0.002747 | 0.1668 | 800 | 728.0 | d63f7aeda6ec5c1e |
| 14 | p2_hold_pct_clay_asof | delta_vs_prior | - | +0.002831 | 0.1084 | 800 | 742.3 | de356e766fbe03dc |
| 15 | p1_hold_pct_clay_asof | ratio_to_opponent | - | +0.002866 | 0.0805 | 800 | 787.0 | 96474b0917948d88 |
| 16 | p2_hold_pct_clay_asof | ew | {'halflife': 20} | +0.002885 | 0.0446 | 800 | 800.0 | 978bb9cbac2c0339 |
| 17 | p2_hold_pct_grass_asof | rank_in_league | - | +0.003028 | 0.0363 | 800 | 783.6 | 1882a24afe0726ab |
| 18 | p2_svpts_won_grass_asof | rank_in_league | - | +0.003069 | 0.0369 | 800 | 779.8 | 260191f79d7884a9 |
| 19 | p2_svpts_won_clay_asof | ew | {'halflife': 5} | +0.003091 | 0.0164 | 800 | 800.0 | 680533ef526dc5c9 |
| 20 | p2_hold_pct_clay_asof | ew | {'halflife': 10} | +0.003111 | 0.0400 | 800 | 800.0 | ef263fc6a2fe6b4d |

### tennis_setdetail (2026-W36)
| rank | feature | transform | params | delta (model - incumbent) | screen DM p | n | n_eff | hash |
|---|---|---|---|---|---|---|---|---|
| 1 | p2_close_set_rate_grass_asof | raw | - | +0.000877 | 0.5638 | 800 | 736.1 | c955fbd9431b68f3 |
| 2 | p2_close_set_rate_grass_asof | z_vs_league | - | +0.000884 | 0.5609 | 800 | 736.0 | 87b7779a2f90eadb |
| 3 | p1_avg_games_per_set_asof | delta_vs_prior | - | +0.001202 | 0.6684 | 800 | 446.7 | 2245955363c673ac |
| 4 | p2_close_set_rate_grass_asof | rank_in_league | - | +0.001389 | 0.4092 | 800 | 767.9 | a861282b1125ba2d |
| 5 | p1_avg_games_per_set_grass_asof | ratio_to_opponent | - | +0.001527 | 0.1484 | 800 | 800.0 | 1797b8daba4acc64 |
| 6 | p1_close_set_rate_asof | delta_vs_prior | - | +0.001544 | 0.5399 | 800 | 479.1 | 7dbc94a964133162 |
| 7 | p2_avg_games_per_set_grass_asof | raw | - | +0.001587 | 0.2088 | 800 | 800.0 | ffac3d7170428a16 |
| 8 | p2_avg_games_per_set_grass_asof | z_vs_league | - | +0.001589 | 0.2084 | 800 | 800.0 | 5e2109359de4eb76 |
| 9 | p1_tiebreak_win_pct_grass_asof | delta_vs_prior | - | +0.001598 | 0.5076 | 800 | 782.1 | ac5eacba000de067 |
| 10 | p2_avg_games_per_set_clay_asof | raw | - | +0.001712 | 0.1893 | 800 | 800.0 | 69531911f74b8df6 |
| 11 | tiebreak_win_pct_asof_diff | delta_vs_prior | - | +0.001714 | 0.3849 | 800 | 647.5 | dee69264ec657302 |
| 12 | p2_avg_games_per_set_clay_asof | z_vs_league | - | +0.001714 | 0.1892 | 800 | 800.0 | d0b6c860410e1917 |
| 13 | p2_tiebreak_win_pct_asof | delta_vs_prior | - | +0.001827 | 0.3457 | 800 | 660.3 | 37a522372e7fd008 |
| 14 | p1_sets_dropped_rate_grass_asof | ratio_to_opponent | - | +0.002080 | 0.0755 | 800 | 800.0 | 9dfcf2c4017e0c33 |
| 15 | p2_avg_games_per_set_clay_asof | rank_in_league | - | +0.002121 | 0.1184 | 800 | 782.2 | 7810d9768bddccb7 |
| 16 | p1_sets_dropped_rate_hard_asof | delta_vs_prior | - | +0.002231 | 0.4682 | 800 | 404.0 | b4b946cf22832060 |
| 17 | p2_sets_dropped_rate_clay_asof | rank_in_league | - | +0.002268 | 0.1359 | 800 | 667.2 | bf757bcc8c374267 |
| 18 | p2_tiebreak_win_pct_clay_asof | raw | - | +0.002270 | 0.1166 | 800 | 776.8 | 66789f3034dc4be1 |
| 19 | p2_tiebreak_win_pct_clay_asof | z_vs_league | - | +0.002270 | 0.1165 | 800 | 777.0 | f199e8e9bc9874bf |
| 20 | p1_avg_games_per_set_clay_asof | delta_vs_prior | - | +0.002318 | 0.1984 | 800 | 597.3 | 0b61bb03aa605003 |


## NOT VERIFIED
- No T2/T3 was run by this lane; nothing on this list has a verdict. The list is input to a charge
  the orchestrator releases later, one at a time, on the VERDICT partition.
- The NBA/MLB incumbent is p_base (Elo), not a close: an NBA "beat" is not a close-relative result.
- The screen refits the incumbent's slope, so the null expectation of delta is not zero; the
  recalibrated-incumbent reference above is one constant-feature run per sport, not a permutation null.
- soccer/tennis states carry `vintage: SYNTHETIC` (S34): T0's vintage assertion passes on a
  constructed 12:00 state_ts and 00:00 availability, including for the close itself.
- live_tick families were not screened at all (no in-game corpus in this lane); they are refused by
  name, not measured.
- The walk-forward refit cadence (50 rows) and MIN_FIT_ROWS (30) are this lane's choices, not prereg.
- `screened_n` per family per ISO week is the `screened` column above; it does not yet enter K (SF-2).
- The DM p of a SCREEN lives in the archive only (`screen_p`), not in `result.raw_p`, so
  `results_db.family_p_values` (F2-owned, no tier filter) keeps pricing charged trials only.
- The wall time is one local run on a shared box while three other lanes ran; screens/hour is that
  measurement, not a ceiling.
