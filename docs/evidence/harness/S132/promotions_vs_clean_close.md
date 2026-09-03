screens=945 families=11 promoted=216 rule=v1 top_n=20 prereg=b2b2ea5a0fe2bd4adaf327aa38e546b49ca0eec3
distribution: {'delta>=0': 902, 'delta<0': 43}
| family | iso_week | screened | beat incumbent (delta<0) | promoted | best delta | best n_eff | incumbent | partition sha (screen) |
|---|---|---|---|---|---|---|---|---|
| mlb_bullpen_relief_chains | 2026-W36 | 32 | 0 | 20 | +0.002257 | 460.0 | devigged_close | 5802cb7ab18516c8 |
| mlb_gate | 2026-W36 | 16 | 0 | 16 | +0.002568 | 460.0 | devigged_close | 5802cb7ab18516c8 |
| nba_boxdetail | 2026-W36 | 250 | 0 | 20 | +0.000036 | 313.0 | first_inplay_tick+pregame_venue_close | 00ce09cab113d25d |
| nba_carryover | 2026-W36 | 50 | 5 | 20 | -0.000602 | 313.0 | first_inplay_tick+pregame_venue_close | 00ce09cab113d25d |
| nba_defender_rollup | 2026-W36 | 72 | 10 | 20 | -0.000855 | 313.0 | first_inplay_tick+pregame_venue_close | 00ce09cab113d25d |
| nba_gate | 2026-W36 | 88 | 12 | 20 | -0.002302 | 277.5 | first_inplay_tick+pregame_venue_close | 00ce09cab113d25d |
| nba_opp_allowed | 2026-W36 | 120 | 8 | 20 | -0.001708 | 313.0 | first_inplay_tick+pregame_venue_close | 00ce09cab113d25d |
| nba_player_adv | 2026-W36 | 48 | 0 | 20 | +0.000233 | 242.8 | first_inplay_tick+pregame_venue_close | 00ce09cab113d25d |
| nba_player_value_features | 2026-W36 | 32 | 0 | 20 | +0.000072 | 313.0 | first_inplay_tick+pregame_venue_close | 00ce09cab113d25d |
| nba_quarter_shape | 2026-W36 | 125 | 4 | 20 | -0.002079 | 313.0 | first_inplay_tick+pregame_venue_close | 00ce09cab113d25d |
| nba_team_adv | 2026-W36 | 112 | 4 | 20 | -0.001620 | 252.8 | first_inplay_tick+pregame_venue_close | 00ce09cab113d25d |

## Candidates per family (SCREEN deltas -- NOT findings)

### mlb_bullpen_relief_chains (2026-W36)
| rank | feature | transform | params | delta (model - incumbent) | screen DM p | n | n_eff | hash |
|---|---|---|---|---|---|---|---|---|
| 1 | is_b2b | ew | {'halflife': 20} | +0.002257 | 0.1281 | 460 | 460.0 | b7616ca18a6e8942 |
| 2 | is_b2b | ew | {'halflife': 10} | +0.002275 | 0.1231 | 460 | 460.0 | 90bed5c40956ec8a |
| 3 | is_b2b | ew | {'halflife': 5} | +0.002319 | 0.1126 | 460 | 460.0 | 57ad4c48d6d33773 |
| 4 | is_b2b | ew | {'halflife': 3} | +0.002383 | 0.0997 | 460 | 460.0 | 89f4cec0d5cf6242 |
| 5 | battersFaced | ew | {'halflife': 20} | +0.002641 | 0.0971 | 460 | 386.0 | 81ade68f48dd2f73 |
| 6 | battersFaced | ew | {'halflife': 10} | +0.002659 | 0.0959 | 460 | 385.1 | eb7239be41a69edd |
| 7 | battersFaced | ew | {'halflife': 5} | +0.002680 | 0.0963 | 460 | 381.7 | f7bbb62fb7a58427 |
| 8 | battersFaced | ew | {'halflife': 3} | +0.002683 | 0.1016 | 460 | 374.9 | 58535a601826fd09 |
| 9 | appearances_last_3d | ew | {'halflife': 20} | +0.002847 | 0.0628 | 460 | 448.9 | f22dddfd5f9b4e68 |
| 10 | appearances_last_3d | ew | {'halflife': 10} | +0.002863 | 0.0614 | 460 | 448.3 | 2094dc9dad1866a4 |
| 11 | rest_days | delta_vs_prior | - | +0.002874 | 0.2410 | 460 | 306.1 | 1b35f0fc2ad51d44 |
| 12 | appearances_last_3d | ew | {'halflife': 5} | +0.002904 | 0.0581 | 460 | 447.5 | b6c1ac9c88896a21 |
| 13 | appearances_last_3d | ew | {'halflife': 3} | +0.002963 | 0.0540 | 460 | 445.8 | c1bf12062794da5f |
| 14 | battersFaced | delta_vs_prior | - | +0.002992 | 0.1924 | 460 | 460.0 | 4ff7c6e88d8565bd |
| 15 | rest_days | ew | {'halflife': 20} | +0.003189 | 0.1028 | 460 | 460.0 | 0e35ba35efbf7481 |
| 16 | rest_days | ew | {'halflife': 10} | +0.003232 | 0.0967 | 460 | 460.0 | 6116608ea7d5d9e6 |
| 17 | is_b2b | raw | - | +0.003266 | 0.0641 | 460 | 412.1 | fa2741d1dc3593a9 |
| 18 | battersFaced | rank_in_league | - | +0.003315 | 0.0513 | 460 | 426.0 | fbc888e9789c3790 |
| 19 | rest_days | ew | {'halflife': 5} | +0.003322 | 0.0848 | 460 | 460.0 | 281f99cf97319bf7 |
| 20 | rest_days | z_vs_league | - | +0.003413 | 0.0848 | 460 | 460.0 | 06aa3b4a6346834a |

### mlb_gate (2026-W36)
| rank | feature | transform | params | delta (model - incumbent) | screen DM p | n | n_eff | hash |
|---|---|---|---|---|---|---|---|---|
| 1 | p_base | ew | {'halflife': 3} | +0.002568 | 0.1249 | 460 | 460.0 | 1af403180ab37ce6 |
| 2 | p_home_elo | ew | {'halflife': 3} | +0.002568 | 0.1249 | 460 | 460.0 | dcf0554d2e0d6dac |
| 3 | p_home_elo | ew | {'halflife': 5} | +0.002669 | 0.1189 | 460 | 460.0 | 62d11c015bf7bf07 |
| 4 | p_base | ew | {'halflife': 5} | +0.002669 | 0.1189 | 460 | 460.0 | 6b957d3d3bd61ec7 |
| 5 | p_home_elo | ew | {'halflife': 10} | +0.002751 | 0.1141 | 460 | 460.0 | c91ad7ccc0321cb6 |
| 6 | p_base | ew | {'halflife': 10} | +0.002751 | 0.1141 | 460 | 460.0 | efef8dc93f97ac5d |
| 7 | p_home_elo | ew | {'halflife': 20} | +0.002785 | 0.1121 | 460 | 460.0 | b1ef09432bfe36e1 |
| 8 | p_base | ew | {'halflife': 20} | +0.002785 | 0.1121 | 460 | 460.0 | e75da921ee317476 |
| 9 | p_home_elo | rank_in_league | - | +0.003260 | 0.0748 | 460 | 333.1 | 20ec4b89eb68fba0 |
| 10 | p_base | rank_in_league | - | +0.003260 | 0.0748 | 460 | 333.1 | 3daf4b893fe3715f |
| 11 | p_home_elo | raw | - | +0.003962 | 0.0568 | 460 | 437.5 | 1a5c2af36be83005 |
| 12 | p_base | raw | - | +0.003962 | 0.0568 | 460 | 437.5 | 5204ddf10a3f2039 |
| 13 | p_home_elo | delta_vs_prior | - | +0.004199 | 0.0787 | 460 | 460.0 | 857216efce16b2f7 |
| 14 | p_base | delta_vs_prior | - | +0.004199 | 0.0787 | 460 | 460.0 | ac62facb7790f0df |
| 15 | p_home_elo | z_vs_league | - | +0.004383 | 0.0767 | 460 | 382.8 | 00fe9b94e5434470 |
| 16 | p_base | z_vs_league | - | +0.004383 | 0.0767 | 460 | 382.8 | 09e038facbd1be62 |

### nba_boxdetail (2026-W36)
| rank | feature | transform | params | delta (model - incumbent) | screen DM p | n | n_eff | hash |
|---|---|---|---|---|---|---|---|---|
| 1 | home_foul_trouble_asof | ew | {'halflife': 20} | +0.000036 | 0.9857 | 313 | 313.0 | 7d75d156b954b256 |
| 2 | home_foul_trouble_asof | ew | {'halflife': 10} | +0.000106 | 0.9575 | 313 | 313.0 | f712160ea08dd9be |
| 3 | home_foul_trouble_asof | ew | {'halflife': 5} | +0.000241 | 0.9025 | 313 | 313.0 | 788863413e3268b9 |
| 4 | tov_pts_l10_diff_asof | delta_vs_prior | - | +0.000269 | 0.9259 | 313 | 313.0 | bbbadc7ac47c8403 |
| 5 | home_paint_pts_l10_asof | delta_vs_prior | - | +0.000344 | 0.8737 | 313 | 308.9 | f01d07a9bb88e0dd |
| 6 | home_foul_trouble_asof | ew | {'halflife': 3} | +0.000403 | 0.8360 | 313 | 313.0 | 5d8844e6bd640c37 |
| 7 | away_tov_pts_asof | ew | {'halflife': 3} | +0.000419 | 0.8686 | 313 | 313.0 | 5f96031718f1afcc |
| 8 | away_tov_pts_asof | ew | {'halflife': 5} | +0.000530 | 0.8349 | 313 | 313.0 | 2fa2540aa3e52031 |
| 9 | away_tov_pts_l10_asof | ew | {'halflife': 3} | +0.000550 | 0.8581 | 313 | 293.7 | d172e2584f49d2d5 |
| 10 | away_tov_pts_asof | ew | {'halflife': 10} | +0.000690 | 0.7867 | 313 | 313.0 | f4500a1fbe1a84b3 |
| 11 | away_tov_pts_l10_asof | ew | {'halflife': 5} | +0.000749 | 0.8030 | 313 | 294.5 | 8df1c1c4ae10ae91 |
| 12 | home_tov_pts_l10_asof | delta_vs_prior | - | +0.000793 | 0.7396 | 313 | 313.0 | eb74634551148209 |
| 13 | away_tov_pts_asof | ew | {'halflife': 20} | +0.000794 | 0.7560 | 313 | 313.0 | 0d272be60b45db1a |
| 14 | tov_pts_l10_diff_asof | ew | {'halflife': 3} | +0.000816 | 0.7975 | 313 | 313.0 | 675cacd4c19ffa57 |
| 15 | home_foul_trouble_l10_asof | ew | {'halflife': 20} | +0.000819 | 0.6862 | 313 | 313.0 | e99e51ec28df3244 |
| 16 | home_tov_pts_asof | delta_vs_prior | - | +0.000851 | 0.6339 | 313 | 313.0 | 02ca4bb131f7dfac |
| 17 | away_foul_trouble_asof | ew | {'halflife': 20} | +0.000867 | 0.6252 | 313 | 313.0 | d1d1c60852c247b3 |
| 18 | home_foul_trouble_l10_asof | ew | {'halflife': 10} | +0.000871 | 0.6650 | 313 | 313.0 | 6923ecd84b5f60c0 |
| 19 | away_foul_trouble_asof | ew | {'halflife': 10} | +0.000876 | 0.6232 | 313 | 313.0 | ea2be906b2024606 |
| 20 | away_foul_trouble_asof | ew | {'halflife': 5} | +0.000894 | 0.6196 | 313 | 313.0 | 8ce3a878f00c110c |

### nba_carryover (2026-W36)
| rank | feature | transform | params | delta (model - incumbent) | screen DM p | n | n_eff | hash |
|---|---|---|---|---|---|---|---|---|
| 1 | home_heavy_min_load_asof | ew | {'halflife': 3} | -0.000602 | 0.7303 | 313 | 313.0 | 5e968760528b78c9 |
| 2 | home_heavy_min_load_asof | ew | {'halflife': 5} | -0.000574 | 0.7442 | 313 | 313.0 | 42af0954f9fd2590 |
| 3 | home_heavy_min_load_asof | ew | {'halflife': 10} | -0.000536 | 0.7631 | 313 | 313.0 | 777982676e814dc6 |
| 4 | home_heavy_min_load_asof | ew | {'halflife': 20} | -0.000512 | 0.7749 | 313 | 313.0 | 3dbd01a37730e5db |
| 5 | home_rest_days_asof | delta_vs_prior | - | -0.000107 | 0.9607 | 313 | 313.0 | 5b3d9fa6556b9dd6 |
| 6 | away_heavy_min_load_asof | ew | {'halflife': 3} | +0.000808 | 0.7168 | 313 | 293.4 | 397543b58671b404 |
| 7 | away_heavy_min_load_asof | ew | {'halflife': 5} | +0.000914 | 0.6706 | 313 | 304.7 | 9aa16123efcb981d |
| 8 | rest_days_diff_asof | ew | {'halflife': 3} | +0.000968 | 0.6036 | 313 | 313.0 | 45be24ea41dfdaf9 |
| 9 | away_heavy_min_load_asof | ew | {'halflife': 10} | +0.000999 | 0.6330 | 313 | 313.0 | 553692d75b372fb8 |
| 10 | home_heavy_min_load_asof | delta_vs_prior | - | +0.001012 | 0.6770 | 313 | 242.4 | 72471645daacb1a2 |
| 11 | rest_days_diff_asof | ew | {'halflife': 5} | +0.001012 | 0.5836 | 313 | 313.0 | ef61a0ead6b3bbb8 |
| 12 | away_heavy_min_load_asof | ew | {'halflife': 20} | +0.001042 | 0.6142 | 313 | 313.0 | 9e22c0e945d12195 |
| 13 | rest_days_diff_asof | ew | {'halflife': 10} | +0.001057 | 0.5658 | 313 | 313.0 | a4a76e29a1add6fe |
| 14 | rest_days_diff_asof | ew | {'halflife': 20} | +0.001082 | 0.5565 | 313 | 313.0 | e7fa27b1950cfa4a |
| 15 | heavy_min_load_diff_asof | delta_vs_prior | - | +0.001174 | 0.5899 | 313 | 313.0 | 1541070eea738303 |
| 16 | heavy_min_load_diff_asof | ew | {'halflife': 3} | +0.001237 | 0.4958 | 313 | 313.0 | 1a1629528fdd5514 |
| 17 | heavy_min_load_diff_asof | ew | {'halflife': 5} | +0.001245 | 0.4906 | 313 | 313.0 | 48b71e48e6c887fa |
| 18 | heavy_min_load_diff_asof | ew | {'halflife': 10} | +0.001251 | 0.4870 | 313 | 313.0 | f58098fcae55ed55 |
| 19 | heavy_min_load_diff_asof | ew | {'halflife': 20} | +0.001255 | 0.4851 | 313 | 313.0 | ffa3675665240aaa |
| 20 | away_heavy_min_load_asof | delta_vs_prior | - | +0.001331 | 0.7016 | 313 | 239.5 | 75735cdc94b796a6 |

### nba_defender_rollup (2026-W36)
| rank | feature | transform | params | delta (model - incumbent) | screen DM p | n | n_eff | hash |
|---|---|---|---|---|---|---|---|---|
| 1 | away_def_pts_allowed_per36_asof | ew | {'halflife': 3} | -0.000855 | 0.6153 | 313 | 313.0 | a545ec90661b68d6 |
| 2 | away_def_pts_allowed_per36_asof | ew | {'halflife': 5} | -0.000777 | 0.6489 | 313 | 313.0 | b698938aa4993416 |
| 3 | away_def_pts_allowed_per36_asof | ew | {'halflife': 10} | -0.000699 | 0.6860 | 313 | 313.0 | 166280640d31a7c7 |
| 4 | away_def_pts_allowed_per36_asof | ew | {'halflife': 20} | -0.000652 | 0.7091 | 313 | 313.0 | 0754c3e7080bca6f |
| 5 | away_def_matchup_min_asof | ew | {'halflife': 5} | -0.000548 | 0.8306 | 313 | 313.0 | 7c2d9c18e4789296 |
| 6 | away_def_matchup_min_asof | ew | {'halflife': 3} | -0.000538 | 0.8328 | 313 | 313.0 | bdcbbc178f83f2a7 |
| 7 | away_def_matchup_min_asof | ew | {'halflife': 10} | -0.000492 | 0.8482 | 313 | 313.0 | 7764c709c94c46dd |
| 8 | away_def_matchup_min_asof | ew | {'halflife': 20} | -0.000440 | 0.8644 | 313 | 313.0 | a1406ff90b0572cd |
| 9 | def_matchup_min_diff_asof | ew | {'halflife': 20} | -0.000211 | 0.9573 | 313 | 279.6 | 5944a638d903abef |
| 10 | def_matchup_min_diff_asof | ew | {'halflife': 10} | -0.000149 | 0.9699 | 313 | 276.8 | 7b95384d2d294162 |
| 11 | def_matchup_min_diff_asof | ew | {'halflife': 5} | +0.000011 | 0.9978 | 313 | 272.0 | c7cd05d2db302050 |
| 12 | def_matchup_min_diff_asof | ew | {'halflife': 3} | +0.000263 | 0.9484 | 313 | 268.0 | aa218e80ebc52201 |
| 13 | def_pts_allowed_per36_diff_asof | ew | {'halflife': 3} | +0.000307 | 0.8707 | 313 | 313.0 | 19a5df457306a46a |
| 14 | away_def_fg_pct_allowed_asof | ew | {'halflife': 3} | +0.000353 | 0.8408 | 313 | 313.0 | 7477572888842f96 |
| 15 | away_def_fg_pct_allowed_asof | ew | {'halflife': 5} | +0.000411 | 0.8146 | 313 | 313.0 | 0ca10849a8715df2 |
| 16 | away_def_fg_pct_allowed_asof | ew | {'halflife': 10} | +0.000462 | 0.7924 | 313 | 313.0 | bbef60be13ff253f |
| 17 | away_def_fg_pct_allowed_asof | ew | {'halflife': 20} | +0.000489 | 0.7810 | 313 | 313.0 | 29f63508849d0e00 |
| 18 | def_pts_allowed_per36_diff_asof | ew | {'halflife': 5} | +0.000545 | 0.7778 | 313 | 313.0 | a4a487fd311e4dd1 |
| 19 | home_def_blocks_per_game_asof | ew | {'halflife': 20} | +0.000581 | 0.7440 | 313 | 313.0 | 6f30d3dc6c8eb3ce |
| 20 | home_def_blocks_per_game_asof | ew | {'halflife': 10} | +0.000608 | 0.7331 | 313 | 313.0 | c43c25688bd5bda1 |

### nba_gate (2026-W36)
| rank | feature | transform | params | delta (model - incumbent) | screen DM p | n | n_eff | hash |
|---|---|---|---|---|---|---|---|---|
| 1 | oreb_pg_diff_asof | ew | {'halflife': 20} | -0.002302 | 0.3932 | 313 | 277.5 | d5be508f1e421200 |
| 2 | oreb_pg_diff_asof | ew | {'halflife': 10} | -0.002272 | 0.3966 | 313 | 274.8 | 7965465abc76270e |
| 3 | oreb_pg_diff_asof | ew | {'halflife': 5} | -0.002190 | 0.4086 | 313 | 270.3 | dde0fb143dd2d925 |
| 4 | oreb_pg_diff_asof | ew | {'halflife': 3} | -0.002058 | 0.4312 | 313 | 266.4 | 59fb248e8391bde7 |
| 5 | pace_diff_asof | ew | {'halflife': 20} | -0.001620 | 0.5469 | 313 | 252.8 | 951ad286b957639b |
| 6 | pace_diff_asof | ew | {'halflife': 10} | -0.001608 | 0.5491 | 313 | 251.1 | 0704bb6a5ad03559 |
| 7 | pace_diff_asof | ew | {'halflife': 5} | -0.001555 | 0.5617 | 313 | 248.2 | ecb2fd0d540ffcfe |
| 8 | pace_diff_asof | ew | {'halflife': 3} | -0.001433 | 0.5926 | 313 | 245.0 | 85b0101fb9436446 |
| 9 | stl_diff_asof | ew | {'halflife': 5} | -0.000922 | 0.7288 | 313 | 313.0 | e82607f8595c80b6 |
| 10 | stl_diff_asof | ew | {'halflife': 3} | -0.000921 | 0.7248 | 313 | 313.0 | d7638803affc4c82 |
| 11 | stl_diff_asof | ew | {'halflife': 10} | -0.000913 | 0.7345 | 313 | 313.0 | c7aa56d593fe93e2 |
| 12 | stl_diff_asof | ew | {'halflife': 20} | -0.000907 | 0.7379 | 313 | 313.0 | 9d612e4540e9dc93 |
| 13 | stl_diff_asof | delta_vs_prior | - | +0.000653 | 0.7306 | 313 | 313.0 | 5ff9383b5c060122 |
| 14 | dreb_diff_asof | ew | {'halflife': 20} | +0.000833 | 0.6605 | 313 | 313.0 | 0a90ed20dbf1bfbf |
| 15 | dreb_diff_asof | ew | {'halflife': 10} | +0.000892 | 0.6402 | 313 | 313.0 | 370ae6fa30374dea |
| 16 | dreb_diff_asof | ew | {'halflife': 5} | +0.000986 | 0.6100 | 313 | 313.0 | d71386a18feea387 |
| 17 | fg3m_diff_asof | delta_vs_prior | - | +0.001036 | 0.6569 | 313 | 305.1 | 1b41f72268a5fc58 |
| 18 | oreb_pg_diff_asof | delta_vs_prior | - | +0.001064 | 0.5681 | 313 | 313.0 | 8b012e942acd5e02 |
| 19 | dreb_diff_asof | ew | {'halflife': 3} | +0.001065 | 0.5875 | 313 | 313.0 | 3a4e3475702e1696 |
| 20 | fg3m_diff_asof | ew | {'halflife': 3} | +0.001100 | 0.5681 | 313 | 313.0 | 1d62556555b8c0c9 |

### nba_opp_allowed (2026-W36)
| rank | feature | transform | params | delta (model - incumbent) | screen DM p | n | n_eff | hash |
|---|---|---|---|---|---|---|---|---|
| 1 | opp_reb_allowed_asof | ew | {'halflife': 3} | -0.001708 | 0.4247 | 313 | 313.0 | b4ec9b2b6d93fcb2 |
| 2 | opp_reb_allowed_vs_league | ew | {'halflife': 3} | -0.001693 | 0.4303 | 313 | 313.0 | 3dbd5b6f9d5b18f6 |
| 3 | opp_reb_allowed_asof | ew | {'halflife': 5} | -0.001432 | 0.4980 | 313 | 313.0 | 8b71dde570e0424b |
| 4 | opp_reb_allowed_vs_league | ew | {'halflife': 5} | -0.001415 | 0.5048 | 313 | 313.0 | 0374133d0ef33a0f |
| 5 | opp_reb_allowed_asof | ew | {'halflife': 10} | -0.001216 | 0.5633 | 313 | 313.0 | b91ef96ac019c7cb |
| 6 | opp_reb_allowed_vs_league | ew | {'halflife': 10} | -0.001196 | 0.5710 | 313 | 313.0 | e28801d8f59272a9 |
| 7 | opp_reb_allowed_asof | ew | {'halflife': 20} | -0.001108 | 0.5981 | 313 | 313.0 | 697b38bd190117fd |
| 8 | opp_reb_allowed_vs_league | ew | {'halflife': 20} | -0.001087 | 0.6062 | 313 | 313.0 | 05a4566adec129a9 |
| 9 | opp_blk_allowed_vs_league | delta_vs_prior | - | +0.000405 | 0.8832 | 313 | 313.0 | 0e2190761fe8421d |
| 10 | opp_blk_allowed_asof | delta_vs_prior | - | +0.000409 | 0.8816 | 313 | 313.0 | ea13b95cf791d0c9 |
| 11 | n_games_asof | delta_vs_prior | - | +0.000810 | 0.6722 | 313 | 313.0 | 6db51d64c8603bda |
| 12 | opp_fg3m_allowed_asof | ew | {'halflife': 20} | +0.000866 | 0.6372 | 313 | 313.0 | b08c61f2a6d6ddd7 |
| 13 | opp_fg3m_allowed_vs_league | ew | {'halflife': 20} | +0.000866 | 0.6369 | 313 | 313.0 | 6a1321b66ffa680a |
| 14 | opp_fg3m_allowed_asof | ew | {'halflife': 10} | +0.000873 | 0.6355 | 313 | 313.0 | 869ab8f3e9bcdc83 |
| 15 | opp_fg3m_allowed_vs_league | ew | {'halflife': 10} | +0.000874 | 0.6350 | 313 | 313.0 | b4920a0980bebbf5 |
| 16 | opp_fg3m_allowed_asof | ew | {'halflife': 5} | +0.000883 | 0.6341 | 313 | 313.0 | cb2dadbbb1262a32 |
| 17 | opp_fg3m_allowed_vs_league | ew | {'halflife': 5} | +0.000885 | 0.6334 | 313 | 313.0 | 258f5ef00f6bba8f |
| 18 | opp_fg3m_allowed_asof | ew | {'halflife': 3} | +0.000885 | 0.6370 | 313 | 313.0 | 69194f98ebb2f37a |
| 19 | opp_fg3m_allowed_vs_league | ew | {'halflife': 3} | +0.000888 | 0.6360 | 313 | 313.0 | e4407070e9508fac |
| 20 | opp_fg3m_allowed_asof | delta_vs_prior | - | +0.001245 | 0.5107 | 313 | 313.0 | e1868491bb8c6d96 |

### nba_player_adv (2026-W36)
| rank | feature | transform | params | delta (model - incumbent) | screen DM p | n | n_eff | hash |
|---|---|---|---|---|---|---|---|---|
| 1 | usagepercentage_asof | ew | {'halflife': 20} | +0.000233 | 0.9239 | 313 | 242.8 | 0948d670ca8f60ff |
| 2 | usagepercentage_asof | ew | {'halflife': 10} | +0.000261 | 0.9150 | 313 | 243.2 | a9ea9c0bee02895e |
| 3 | usagepercentage_asof | ew | {'halflife': 5} | +0.000310 | 0.8988 | 313 | 243.9 | fc203ac8c7562450 |
| 4 | usagepercentage_asof | ew | {'halflife': 3} | +0.000359 | 0.8831 | 313 | 245.1 | 42d0b1a45bc88a96 |
| 5 | offensiverating_asof | delta_vs_prior | - | +0.000934 | 0.7271 | 313 | 261.6 | 92ca88f6ec5855a9 |
| 6 | possessions_asof | ew | {'halflife': 3} | +0.000944 | 0.6361 | 313 | 300.0 | 5e727e9704e7a891 |
| 7 | possessions_asof | ew | {'halflife': 5} | +0.000994 | 0.6165 | 313 | 303.1 | 4274c5eb9fb6ebb6 |
| 8 | possessions_asof | ew | {'halflife': 10} | +0.001033 | 0.6013 | 313 | 306.2 | 6e1d71ce805c0da8 |
| 9 | possessions_asof | ew | {'halflife': 20} | +0.001052 | 0.5939 | 313 | 307.9 | 1d73ddca49297e8a |
| 10 | n_prior | ew | {'halflife': 10} | +0.001366 | 0.5043 | 313 | 313.0 | 3d2c27c064f2e92c |
| 11 | n_prior | ew | {'halflife': 20} | +0.001366 | 0.5044 | 313 | 313.0 | 5a5a7ac15db3ae81 |
| 12 | n_prior | ew | {'halflife': 5} | +0.001367 | 0.5037 | 313 | 313.0 | f5fc9c850dbf4507 |
| 13 | n_prior | ew | {'halflife': 3} | +0.001370 | 0.5026 | 313 | 313.0 | 3286eaf49ad3f98e |
| 14 | usagepercentage_asof | delta_vs_prior | - | +0.001644 | 0.4070 | 313 | 313.0 | 3cd953eefd1544a5 |
| 15 | offensiverating_asof | ew | {'halflife': 3} | +0.001723 | 0.4865 | 313 | 291.6 | 2e38f17ef60e08b2 |
| 16 | offensiverating_asof | ew | {'halflife': 5} | +0.001725 | 0.4855 | 313 | 294.4 | cbfadad19f951510 |
| 17 | offensiverating_asof | ew | {'halflife': 10} | +0.001734 | 0.4831 | 313 | 296.7 | f7cb30e426db8cf5 |
| 18 | offensiverating_asof | ew | {'halflife': 20} | +0.001740 | 0.4816 | 313 | 297.9 | 8bb9c1004b4d9313 |
| 19 | defensiverating_asof | ew | {'halflife': 20} | +0.001962 | 0.3735 | 313 | 268.8 | 8e9e5529eba016b5 |
| 20 | defensiverating_asof | ew | {'halflife': 10} | +0.001989 | 0.3692 | 313 | 268.0 | 8ef617b4f71cd259 |

### nba_player_value_features (2026-W36)
| rank | feature | transform | params | delta (model - incumbent) | screen DM p | n | n_eff | hash |
|---|---|---|---|---|---|---|---|---|
| 1 | continuity | ew | {'halflife': 20} | +0.000072 | 0.9750 | 313 | 313.0 | f964bfebed763476 |
| 2 | continuity | ew | {'halflife': 10} | +0.000208 | 0.9275 | 313 | 313.0 | 9b3b37d81f592236 |
| 3 | continuity | delta_vs_prior | - | +0.000384 | 0.8455 | 313 | 313.0 | 6e4af703b81a9b81 |
| 4 | continuity | ew | {'halflife': 5} | +0.000475 | 0.8351 | 313 | 313.0 | 5ca8c06e8f5bb082 |
| 5 | top_heavy | ew | {'halflife': 3} | +0.000779 | 0.6803 | 313 | 313.0 | 158949e8c86fca71 |
| 6 | top_heavy | ew | {'halflife': 5} | +0.000781 | 0.6851 | 313 | 313.0 | fb1d72b9431d4784 |
| 7 | continuity | ew | {'halflife': 3} | +0.000805 | 0.7249 | 313 | 313.0 | 174c1fd40b1696ba |
| 8 | top_heavy | ew | {'halflife': 10} | +0.000819 | 0.6752 | 313 | 313.0 | d13b702bd4669850 |
| 9 | top_heavy | ew | {'halflife': 20} | +0.000849 | 0.6660 | 313 | 313.0 | 8205969be7e3c398 |
| 10 | roster_value_asof | ew | {'halflife': 5} | +0.000955 | 0.6355 | 313 | 313.0 | 026e691ea705b824 |
| 11 | roster_value_asof | ew | {'halflife': 10} | +0.000964 | 0.6341 | 313 | 313.0 | d1684819df42348a |
| 12 | roster_value_asof | ew | {'halflife': 20} | +0.000979 | 0.6297 | 313 | 313.0 | e6f26a5c99c2746b |
| 13 | roster_value_asof | ew | {'halflife': 3} | +0.000990 | 0.6203 | 313 | 313.0 | f9adac90b7e7b080 |
| 14 | continuity | z_vs_league | - | +0.000994 | 0.7715 | 313 | 208.9 | 0d733002328bcd9c |
| 15 | roster_value_asof | z_vs_league | - | +0.001383 | 0.5905 | 313 | 313.0 | 72931651cd2d8fbd |
| 16 | roster_value_asof | delta_vs_prior | - | +0.001816 | 0.4491 | 313 | 313.0 | 060e8d13110cf540 |
| 17 | roster_value_asof | raw | - | +0.001960 | 0.4677 | 313 | 313.0 | 2d2929478979aac0 |
| 18 | top_heavy | delta_vs_prior | - | +0.002207 | 0.2209 | 313 | 313.0 | f02f9607cdc99f8b |
| 19 | star_absence_delta | ew | {'halflife': 20} | +0.002215 | 0.5715 | 313 | 241.7 | fc4246da9ae80281 |
| 20 | star_absence_delta | ew | {'halflife': 10} | +0.002284 | 0.5584 | 313 | 245.3 | 6311976f82484745 |

### nba_quarter_shape (2026-W36)
| rank | feature | transform | params | delta (model - incumbent) | screen DM p | n | n_eff | hash |
|---|---|---|---|---|---|---|---|---|
| 1 | away_q4_margin_asof | ew | {'halflife': 20} | -0.002079 | 0.3027 | 313 | 313.0 | 6b5e7e623fc0eedf |
| 2 | away_q4_margin_asof | ew | {'halflife': 10} | -0.001882 | 0.3476 | 313 | 313.0 | b07cff9cc503f7c7 |
| 3 | away_q4_margin_asof | ew | {'halflife': 5} | -0.001475 | 0.4575 | 313 | 313.0 | bbda5fc9f15a1a00 |
| 4 | away_q4_margin_asof | ew | {'halflife': 3} | -0.000938 | 0.6344 | 313 | 313.0 | 638c272dd98d9989 |
| 5 | diff_q4_margin_asof | ew | {'halflife': 20} | +0.000067 | 0.9776 | 313 | 313.0 | 53729b6122776b83 |
| 6 | away_second_half_margin_asof | ew | {'halflife': 20} | +0.000142 | 0.9365 | 313 | 313.0 | a089720f5aeed7ee |
| 7 | away_second_half_margin_asof | ew | {'halflife': 10} | +0.000165 | 0.9257 | 313 | 313.0 | 68449e5cf5f73a53 |
| 8 | away_second_half_margin_asof | ew | {'halflife': 5} | +0.000233 | 0.8948 | 313 | 313.0 | 5c0b5595f84fea51 |
| 9 | diff_q4_margin_asof | ew | {'halflife': 10} | +0.000267 | 0.9114 | 313 | 313.0 | 2663facc21d29c06 |
| 10 | away_second_half_margin_asof | ew | {'halflife': 3} | +0.000359 | 0.8379 | 313 | 313.0 | b24972230ebfb81f |
| 11 | diff_quarter_volatility_asof | ew | {'halflife': 20} | +0.000541 | 0.7949 | 313 | 308.0 | 268ffbffe77e8469 |
| 12 | diff_quarter_volatility_asof | ew | {'halflife': 10} | +0.000544 | 0.7933 | 313 | 308.8 | 86d5534da0c345e3 |
| 13 | diff_quarter_volatility_asof | ew | {'halflife': 5} | +0.000563 | 0.7854 | 313 | 310.8 | 80cc198a76123f98 |
| 14 | diff_quarter_volatility_asof | ew | {'halflife': 3} | +0.000610 | 0.7668 | 313 | 313.0 | 3315b73f45bf8270 |
| 15 | away_first_half_margin_asof | ew | {'halflife': 20} | +0.000632 | 0.8026 | 313 | 282.0 | 3e1bf9d01a5303d9 |
| 16 | diff_q4_margin_asof | ew | {'halflife': 5} | +0.000646 | 0.7884 | 313 | 313.0 | b8b011bfd3674fbb |
| 17 | home_first_half_margin_asof | delta_vs_prior | - | +0.000700 | 0.7174 | 313 | 313.0 | c877a0addc08fd6f |
| 18 | away_first_half_margin_asof | ew | {'halflife': 10} | +0.000700 | 0.7816 | 313 | 283.2 | 76d01941a35e16b5 |
| 19 | home_quarter_volatility_asof | delta_vs_prior | - | +0.000791 | 0.6881 | 313 | 313.0 | 98879fdb358ac2dd |
| 20 | home_quarter_volatility_asof | ew | {'halflife': 20} | +0.000814 | 0.6970 | 313 | 294.3 | 774e8bc03dbb1579 |

### nba_team_adv (2026-W36)
| rank | feature | transform | params | delta (model - incumbent) | screen DM p | n | n_eff | hash |
|---|---|---|---|---|---|---|---|---|
| 1 | pace_diff_asof | ew | {'halflife': 20} | -0.001620 | 0.5469 | 313 | 252.8 | 951ad286b957639b |
| 2 | pace_diff_asof | ew | {'halflife': 10} | -0.001608 | 0.5491 | 313 | 251.1 | 0704bb6a5ad03559 |
| 3 | pace_diff_asof | ew | {'halflife': 5} | -0.001555 | 0.5617 | 313 | 248.2 | ecb2fd0d540ffcfe |
| 4 | pace_diff_asof | ew | {'halflife': 3} | -0.001433 | 0.5926 | 313 | 245.0 | 85b0101fb9436446 |
| 5 | home_tov_ratio_asof | ew | {'halflife': 20} | +0.000931 | 0.7011 | 313 | 313.0 | 8619d739d98a32fe |
| 6 | home_tov_ratio_asof | ew | {'halflife': 10} | +0.000938 | 0.6987 | 313 | 313.0 | 341560f348eb67cb |
| 7 | home_tov_ratio_asof | ew | {'halflife': 5} | +0.000954 | 0.6937 | 313 | 313.0 | 65f2ab152a7aab71 |
| 8 | home_tov_ratio_asof | ew | {'halflife': 3} | +0.000974 | 0.6869 | 313 | 313.0 | fe6879184ca9a36c |
| 9 | away_dreb_pct_asof | ew | {'halflife': 20} | +0.001011 | 0.5971 | 313 | 313.0 | ae6138742ca60931 |
| 10 | away_dreb_pct_asof | ew | {'halflife': 10} | +0.001024 | 0.5931 | 313 | 313.0 | 77a9f2847930b42f |
| 11 | dreb_pct_diff_asof | ew | {'halflife': 20} | +0.001034 | 0.6410 | 313 | 289.4 | 46876d4d04e09ec6 |
| 12 | dreb_pct_diff_asof | ew | {'halflife': 10} | +0.001037 | 0.6401 | 313 | 289.5 | 2f82e0644c97fb31 |
| 13 | home_oreb_pct_asof | ew | {'halflife': 3} | +0.001043 | 0.5862 | 313 | 313.0 | a4423f70dddc7c93 |
| 14 | dreb_pct_diff_asof | ew | {'halflife': 5} | +0.001044 | 0.6381 | 313 | 289.7 | c2160a65103162d3 |
| 15 | away_dreb_pct_asof | ew | {'halflife': 5} | +0.001050 | 0.5858 | 313 | 313.0 | cf79fc78ae84ccc8 |
| 16 | dreb_pct_diff_asof | ew | {'halflife': 3} | +0.001056 | 0.6352 | 313 | 289.8 | f6aab9590b96e65a |
| 17 | away_dreb_pct_asof | ew | {'halflife': 3} | +0.001082 | 0.5773 | 313 | 313.0 | 9922758ee388cb2c |
| 18 | home_oreb_pct_asof | ew | {'halflife': 5} | +0.001085 | 0.5696 | 313 | 313.0 | 9a93f16bfe8b81aa |
| 19 | home_oreb_pct_asof | ew | {'halflife': 10} | +0.001120 | 0.5562 | 313 | 313.0 | 1e6513d6dd1cfc14 |
| 20 | home_oreb_pct_asof | ew | {'halflife': 20} | +0.001137 | 0.5494 | 313 | 313.0 | edd59cae5e449137 |
