screens=977 families=12 promoted=240 rule=v1 top_n=20 prereg=b2b2ea5a0fe2bd4adaf327aa38e546b49ca0eec3
distribution: {'delta<0': 725, 'delta>=0': 252}
| family | iso_week | screened | beat incumbent (delta<0) | promoted | best delta | best n_eff | incumbent | partition sha (screen) |
|---|---|---|---|---|---|---|---|---|
| mlb_bullpen_relief_chains | 2026-W36 | 32 | 0 | 20 | +0.003090 | 800.0 | p_base | ad743c924c7c4547 |
| mlb_gate | 2026-W36 | 24 | 0 | 20 | +0.002978 | 800.0 | p_base | ad743c924c7c4547 |
| mlb_inning | 2026-W36 | 24 | 0 | 20 | +0.004620 | 623.7 | p_base | ad743c924c7c4547 |
| nba_boxdetail | 2026-W36 | 250 | 211 | 20 | -0.002244 | 800.0 | p_base | 1a32541d44aa7fcb |
| nba_carryover | 2026-W36 | 50 | 40 | 20 | -0.001483 | 800.0 | p_base | 1a32541d44aa7fcb |
| nba_defender_rollup | 2026-W36 | 72 | 61 | 20 | -0.002747 | 711.4 | p_base | 1a32541d44aa7fcb |
| nba_gate | 2026-W36 | 88 | 80 | 20 | -0.002755 | 800.0 | p_base | 1a32541d44aa7fcb |
| nba_opp_allowed | 2026-W36 | 120 | 79 | 20 | -0.001858 | 800.0 | p_base | 1a32541d44aa7fcb |
| nba_player_adv | 2026-W36 | 48 | 43 | 20 | -0.001053 | 800.0 | p_base | 1a32541d44aa7fcb |
| nba_player_value_features | 2026-W36 | 32 | 29 | 20 | -0.005221 | 800.0 | p_base | 1a32541d44aa7fcb |
| nba_quarter_shape | 2026-W36 | 125 | 104 | 20 | -0.001527 | 487.4 | p_base | 1a32541d44aa7fcb |
| nba_team_adv | 2026-W36 | 112 | 78 | 20 | -0.002181 | 752.5 | p_base | 1a32541d44aa7fcb |

## Candidates per family (SCREEN deltas -- NOT findings)

### mlb_bullpen_relief_chains (2026-W36)
| rank | feature | transform | params | delta (model - incumbent) | screen DM p | n | n_eff | hash |
|---|---|---|---|---|---|---|---|---|
| 1 | battersFaced | delta_vs_prior | - | +0.003090 | 0.1714 | 800 | 800.0 | 4ff7c6e88d8565bd |
| 2 | battersFaced | ew | {'halflife': 20} | +0.003405 | 0.1903 | 800 | 723.2 | 81ade68f48dd2f73 |
| 3 | battersFaced | ew | {'halflife': 10} | +0.003531 | 0.1660 | 800 | 682.9 | eb7239be41a69edd |
| 4 | battersFaced | ew | {'halflife': 5} | +0.003620 | 0.1337 | 800 | 682.3 | f7bbb62fb7a58427 |
| 5 | battersFaced | ew | {'halflife': 3} | +0.003794 | 0.0998 | 800 | 704.6 | 58535a601826fd09 |
| 6 | appearances_last_3d | ew | {'halflife': 20} | +0.004493 | 0.0341 | 800 | 760.6 | f22dddfd5f9b4e68 |
| 7 | appearances_last_3d | ew | {'halflife': 10} | +0.004557 | 0.0300 | 800 | 767.7 | 2094dc9dad1866a4 |
| 8 | battersFaced | raw | - | +0.004565 | 0.1049 | 800 | 645.1 | b8bf61622cd4e261 |
| 9 | battersFaced | z_vs_league | - | +0.004579 | 0.1047 | 800 | 644.8 | a3e5b47615a92dba |
| 10 | appearances_last_3d | ew | {'halflife': 5} | +0.004612 | 0.0298 | 800 | 762.3 | b6c1ac9c88896a21 |
| 11 | rest_days | ew | {'halflife': 5} | +0.004643 | 0.0434 | 800 | 702.4 | 281f99cf97319bf7 |
| 12 | rest_days | ew | {'halflife': 3} | +0.004667 | 0.0343 | 800 | 722.5 | 94a49db3ac016277 |
| 13 | appearances_last_3d | ew | {'halflife': 3} | +0.004696 | 0.0302 | 800 | 754.1 | c1bf12062794da5f |
| 14 | appearances_last_3d | rank_in_league | - | +0.004726 | 0.0236 | 800 | 755.4 | 342306b2e17d8097 |
| 15 | is_b2b | ew | {'halflife': 5} | +0.004762 | 0.0381 | 800 | 800.0 | 57ad4c48d6d33773 |
| 16 | is_b2b | ew | {'halflife': 20} | +0.004795 | 0.0290 | 800 | 800.0 | b7616ca18a6e8942 |
| 17 | is_b2b | ew | {'halflife': 3} | +0.004818 | 0.0428 | 800 | 800.0 | 89f4cec0d5cf6242 |
| 18 | is_b2b | ew | {'halflife': 10} | +0.004822 | 0.0297 | 800 | 800.0 | 90bed5c40956ec8a |
| 19 | appearances_last_3d | raw | - | +0.004845 | 0.0288 | 800 | 728.8 | 014b67725914b823 |
| 20 | appearances_last_3d | z_vs_league | - | +0.004857 | 0.0287 | 800 | 728.6 | 84d6b1775747951c |

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

### nba_opp_allowed (2026-W36)
| rank | feature | transform | params | delta (model - incumbent) | screen DM p | n | n_eff | hash |
|---|---|---|---|---|---|---|---|---|
| 1 | opp_fg3m_allowed_vs_league | ew | {'halflife': 20} | -0.001858 | 0.3432 | 800 | 800.0 | 6a1321b66ffa680a |
| 2 | opp_fg3m_allowed_asof | ew | {'halflife': 20} | -0.001856 | 0.3439 | 800 | 800.0 | b08c61f2a6d6ddd7 |
| 3 | opp_fg3m_allowed_vs_league | ew | {'halflife': 10} | -0.001780 | 0.3633 | 800 | 800.0 | b4920a0980bebbf5 |
| 4 | opp_fg3m_allowed_asof | ew | {'halflife': 10} | -0.001777 | 0.3641 | 800 | 800.0 | 869ab8f3e9bcdc83 |
| 5 | opp_reb_allowed_asof | rank_in_league | - | -0.001673 | 0.4461 | 800 | 747.5 | 3fbdbb1e0a57cb28 |
| 6 | opp_fg3m_allowed_asof | rank_in_league | - | -0.001653 | 0.4860 | 800 | 800.0 | 41472b0d3464573f |
| 7 | opp_fg3m_allowed_vs_league | rank_in_league | - | -0.001652 | 0.4868 | 800 | 800.0 | 8aaca2a20a75a189 |
| 8 | opp_fg3m_allowed_vs_league | ew | {'halflife': 5} | -0.001632 | 0.4035 | 800 | 800.0 | 258f5ef00f6bba8f |
| 9 | opp_fg3m_allowed_asof | ew | {'halflife': 5} | -0.001630 | 0.4043 | 800 | 800.0 | cb2dadbbb1262a32 |
| 10 | opp_reb_allowed_vs_league | rank_in_league | - | -0.001588 | 0.4661 | 800 | 752.6 | 08656c18f47107a5 |
| 11 | opp_fg3m_allowed_vs_league | ew | {'halflife': 3} | -0.001478 | 0.4500 | 800 | 800.0 | e4407070e9508fac |
| 12 | opp_fg3m_allowed_asof | ew | {'halflife': 3} | -0.001475 | 0.4510 | 800 | 800.0 | 69194f98ebb2f37a |
| 13 | n_games_asof | ew | {'halflife': 5} | -0.001159 | 0.5711 | 800 | 800.0 | b680edaa6f714494 |
| 14 | n_games_asof | ew | {'halflife': 3} | -0.001139 | 0.5696 | 800 | 800.0 | 94f34494959f1775 |
| 15 | n_games_asof | ew | {'halflife': 10} | -0.001051 | 0.6149 | 800 | 800.0 | 2b607eaa08bb54c9 |
| 16 | opp_stl_allowed_vs_league | rank_in_league | - | -0.001049 | 0.6124 | 800 | 759.6 | 01f102d33b3f2b2c |
| 17 | opp_stl_allowed_asof | rank_in_league | - | -0.001044 | 0.6140 | 800 | 766.0 | 0c279cc047c3e5bb |
| 18 | opp_fg3m_allowed_vs_league | raw | - | -0.001029 | 0.6157 | 800 | 800.0 | aea4b3ce84c9b81d |
| 19 | opp_fg3m_allowed_asof | raw | - | -0.001023 | 0.6176 | 800 | 800.0 | f003ce7dedbedf5d |
| 20 | opp_fg3m_allowed_vs_league | z_vs_league | - | -0.000973 | 0.6426 | 800 | 800.0 | 729605d53db0b069 |

### nba_player_adv (2026-W36)
| rank | feature | transform | params | delta (model - incumbent) | screen DM p | n | n_eff | hash |
|---|---|---|---|---|---|---|---|---|
| 1 | usagepercentage_asof | rank_in_league | - | -0.001053 | 0.5976 | 800 | 800.0 | f59d0adc3a145c75 |
| 2 | offensiverating_asof | ew | {'halflife': 3} | -0.000962 | 0.7082 | 800 | 690.1 | 2e38f17ef60e08b2 |
| 3 | pie_asof | delta_vs_prior | - | -0.000930 | 0.6315 | 800 | 800.0 | 782bee0fcdf1f62d |
| 4 | possessions_asof | rank_in_league | - | -0.000924 | 0.6404 | 800 | 800.0 | 07b5733d409d98a5 |
| 5 | usagepercentage_asof | ew | {'halflife': 20} | -0.000892 | 0.6689 | 800 | 741.6 | 0948d670ca8f60ff |
| 6 | offensiverating_asof | ew | {'halflife': 5} | -0.000882 | 0.7265 | 800 | 702.6 | cbfadad19f951510 |
| 7 | usagepercentage_asof | ew | {'halflife': 10} | -0.000881 | 0.6735 | 800 | 736.2 | a9ea9c0bee02895e |
| 8 | usagepercentage_asof | ew | {'halflife': 5} | -0.000867 | 0.6795 | 800 | 725.2 | fc203ac8c7562450 |
| 9 | usagepercentage_asof | ew | {'halflife': 3} | -0.000862 | 0.6834 | 800 | 711.0 | 42d0b1a45bc88a96 |
| 10 | pie_asof | ew | {'halflife': 5} | -0.000858 | 0.7045 | 800 | 708.6 | 0bc89490e8b07c3d |
| 11 | pie_asof | ew | {'halflife': 3} | -0.000852 | 0.7059 | 800 | 709.4 | e8e7693a929b4898 |
| 12 | pie_asof | ew | {'halflife': 10} | -0.000852 | 0.7071 | 800 | 708.1 | cc453e346d3b3c65 |
| 13 | pie_asof | ew | {'halflife': 20} | -0.000845 | 0.7099 | 800 | 708.2 | 4a658ebbd273683b |
| 14 | offensiverating_asof | ew | {'halflife': 10} | -0.000824 | 0.7412 | 800 | 707.0 | f7cb30e426db8cf5 |
| 15 | offensiverating_asof | ew | {'halflife': 20} | -0.000799 | 0.7477 | 800 | 708.0 | 8bb9c1004b4d9313 |
| 16 | n_prior | delta_vs_prior | - | -0.000670 | 0.7679 | 800 | 800.0 | ff33ecd7d6f9b511 |
| 17 | pie_asof | rank_in_league | - | -0.000668 | 0.7309 | 800 | 800.0 | 1ddf4d7a6dc215a4 |
| 18 | possessions_asof | ew | {'halflife': 3} | -0.000666 | 0.7750 | 800 | 647.9 | 5e727e9704e7a891 |
| 19 | defensiverating_asof | raw | - | -0.000656 | 0.7584 | 800 | 700.7 | a093b8664519b25d |
| 20 | possessions_asof | delta_vs_prior | - | -0.000640 | 0.7253 | 800 | 800.0 | d6687a3db96fb838 |

### nba_player_value_features (2026-W36)
| rank | feature | transform | params | delta (model - incumbent) | screen DM p | n | n_eff | hash |
|---|---|---|---|---|---|---|---|---|
| 1 | continuity | z_vs_league | - | -0.005221 | 0.0404 | 800 | 800.0 | 0d733002328bcd9c |
| 2 | continuity | raw | - | -0.005172 | 0.0411 | 800 | 800.0 | e4101cdd583c3d30 |
| 3 | roster_value_asof | rank_in_league | - | -0.004037 | 0.1555 | 800 | 800.0 | 445d5f16aff64ba6 |
| 4 | top_heavy | z_vs_league | - | -0.003049 | 0.2511 | 800 | 800.0 | ab77b32396eecf66 |
| 5 | roster_value_asof | raw | - | -0.003043 | 0.4108 | 800 | 559.2 | 2d2929478979aac0 |
| 6 | top_heavy | raw | - | -0.003030 | 0.2455 | 800 | 800.0 | 9c117a22c5c641f4 |
| 7 | roster_value_asof | z_vs_league | - | -0.003028 | 0.4132 | 800 | 573.8 | 72931651cd2d8fbd |
| 8 | continuity | rank_in_league | - | -0.002874 | 0.1708 | 800 | 800.0 | 1bc2d97234a1a667 |
| 9 | continuity | delta_vs_prior | - | -0.002750 | 0.2031 | 800 | 800.0 | 6e4af703b81a9b81 |
| 10 | top_heavy | delta_vs_prior | - | -0.002157 | 0.3794 | 800 | 704.7 | f02f9607cdc99f8b |
| 11 | star_absence_delta | ew | {'halflife': 5} | -0.001963 | 0.3712 | 800 | 800.0 | 5369ad06801a0e09 |
| 12 | star_absence_delta | ew | {'halflife': 10} | -0.001930 | 0.3701 | 800 | 800.0 | 6311976f82484745 |
| 13 | star_absence_delta | ew | {'halflife': 20} | -0.001823 | 0.3954 | 800 | 800.0 | fc4246da9ae80281 |
| 14 | star_absence_delta | ew | {'halflife': 3} | -0.001727 | 0.4449 | 800 | 800.0 | d67c883d9128d441 |
| 15 | continuity | ew | {'halflife': 5} | -0.001607 | 0.4031 | 800 | 800.0 | 5ca8c06e8f5bb082 |
| 16 | continuity | ew | {'halflife': 10} | -0.001572 | 0.4118 | 800 | 800.0 | 9b3b37d81f592236 |
| 17 | continuity | ew | {'halflife': 3} | -0.001530 | 0.4338 | 800 | 800.0 | 174c1fd40b1696ba |
| 18 | continuity | ew | {'halflife': 20} | -0.001519 | 0.4307 | 800 | 800.0 | f964bfebed763476 |
| 19 | roster_value_asof | delta_vs_prior | - | -0.001510 | 0.5207 | 800 | 800.0 | 060e8d13110cf540 |
| 20 | star_absence_delta | rank_in_league | - | -0.000648 | 0.7310 | 800 | 800.0 | d0b507f2c58cd35d |

### nba_quarter_shape (2026-W36)
| rank | feature | transform | params | delta (model - incumbent) | screen DM p | n | n_eff | hash |
|---|---|---|---|---|---|---|---|---|
| 1 | home_q1_margin_asof | ratio_to_opponent | - | -0.001527 | 0.6148 | 800 | 487.4 | 6abae87e9e920c5f |
| 2 | diff_q1_margin_asof | delta_vs_prior | - | -0.001513 | 0.4811 | 800 | 775.7 | 1bc3ddf4778a963b |
| 3 | away_q1_margin_asof | ew | {'halflife': 3} | -0.001452 | 0.4634 | 800 | 783.0 | 9ac3d249a54d601d |
| 4 | away_q1_margin_asof | ew | {'halflife': 20} | -0.001405 | 0.4707 | 800 | 800.0 | 9893d5e7a3f41473 |
| 5 | away_q1_margin_asof | ew | {'halflife': 5} | -0.001395 | 0.4784 | 800 | 790.5 | 211e896cf699a7f6 |
| 6 | away_q1_margin_asof | ew | {'halflife': 10} | -0.001386 | 0.4785 | 800 | 800.0 | 394df13873603db2 |
| 7 | away_q1_margin_asof | delta_vs_prior | - | -0.001378 | 0.5631 | 800 | 727.0 | 8f9e9f6497bb8ce4 |
| 8 | away_q4_margin_asof | ew | {'halflife': 20} | -0.001376 | 0.4506 | 800 | 800.0 | 6b5e7e623fc0eedf |
| 9 | home_quarter_volatility_asof | delta_vs_prior | - | -0.001320 | 0.4797 | 800 | 800.0 | 98879fdb358ac2dd |
| 10 | home_second_half_margin_asof | delta_vs_prior | - | -0.001299 | 0.5838 | 800 | 654.4 | 8825a44960e58455 |
| 11 | diff_quarter_volatility_asof | ew | {'halflife': 3} | -0.001293 | 0.5149 | 800 | 795.3 | 3315b73f45bf8270 |
| 12 | diff_first_half_margin_asof | delta_vs_prior | - | -0.001267 | 0.5409 | 800 | 800.0 | 81d1977c9a7af2c0 |
| 13 | diff_quarter_volatility_asof | ew | {'halflife': 5} | -0.001226 | 0.5357 | 800 | 792.3 | 80cc198a76123f98 |
| 14 | away_q4_margin_asof | ew | {'halflife': 10} | -0.001224 | 0.5034 | 800 | 800.0 | b07cff9cc503f7c7 |
| 15 | home_quarter_volatility_asof | ew | {'halflife': 3} | -0.001214 | 0.5346 | 800 | 800.0 | 88b9d0c50e7ddd90 |
| 16 | away_quarter_volatility_asof | delta_vs_prior | - | -0.001188 | 0.5463 | 800 | 772.5 | 45f4326ceea8e330 |
| 17 | away_quarter_volatility_asof | ew | {'halflife': 3} | -0.001187 | 0.5277 | 800 | 800.0 | 8930b72be9dd2725 |
| 18 | home_quarter_volatility_asof | rank_in_league | - | -0.001177 | 0.5557 | 800 | 800.0 | 13dc07770a93b0aa |
| 19 | diff_quarter_volatility_asof | ew | {'halflife': 10} | -0.001165 | 0.5553 | 800 | 790.9 | 86d5534da0c345e3 |
| 20 | home_quarter_volatility_asof | ew | {'halflife': 5} | -0.001148 | 0.5564 | 800 | 800.0 | 8c1ad861f314a2e2 |

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
