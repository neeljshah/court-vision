screens=945 families=11 promoted=216 rule=v1 top_n=20 prereg=b2b2ea5a0fe2bd4adaf327aa38e546b49ca0eec3
distribution: {'delta>=0': 935, 'delta<0': 10}
| family | iso_week | screened | beat incumbent (delta<0) | promoted | best delta | best n_eff | incumbent | partition sha (screen) |
|---|---|---|---|---|---|---|---|---|
| mlb_bullpen_relief_chains | 2026-W36 | 32 | 0 | 20 | +0.003590 | 414.7 | devigged_close | bee51ac662607eb5 |
| mlb_gate | 2026-W36 | 16 | 0 | 16 | +0.003621 | 341.1 | devigged_close | bee51ac662607eb5 |
| nba_boxdetail | 2026-W36 | 250 | 0 | 20 | +0.001183 | 499.0 | first_inplay_tick+pregame_venue_close | 1980f64c6a21fc1e |
| nba_carryover | 2026-W36 | 50 | 0 | 20 | +0.001444 | 399.1 | first_inplay_tick+pregame_venue_close | 1980f64c6a21fc1e |
| nba_defender_rollup | 2026-W36 | 72 | 0 | 20 | +0.001399 | 436.0 | first_inplay_tick+pregame_venue_close | 1980f64c6a21fc1e |
| nba_gate | 2026-W36 | 88 | 4 | 20 | -0.000263 | 349.3 | first_inplay_tick+pregame_venue_close | 1980f64c6a21fc1e |
| nba_opp_allowed | 2026-W36 | 120 | 1 | 20 | -0.000640 | 452.0 | first_inplay_tick+pregame_venue_close | 1980f64c6a21fc1e |
| nba_player_adv | 2026-W36 | 48 | 0 | 20 | +0.000167 | 499.0 | first_inplay_tick+pregame_venue_close | 1980f64c6a21fc1e |
| nba_player_value_features | 2026-W36 | 32 | 1 | 20 | -0.000178 | 373.9 | first_inplay_tick+pregame_venue_close | 1980f64c6a21fc1e |
| nba_quarter_shape | 2026-W36 | 125 | 0 | 20 | +0.000506 | 499.0 | first_inplay_tick+pregame_venue_close | 1980f64c6a21fc1e |
| nba_team_adv | 2026-W36 | 112 | 4 | 20 | -0.000263 | 349.3 | first_inplay_tick+pregame_venue_close | 1980f64c6a21fc1e |

## Candidates per family (SCREEN deltas -- NOT findings)

### mlb_bullpen_relief_chains (2026-W36)
| rank | feature | transform | params | delta (model - incumbent) | screen DM p | n | n_eff | hash |
|---|---|---|---|---|---|---|---|---|
| 1 | is_b2b | raw | - | +0.003590 | 0.0677 | 452 | 414.7 | fa2741d1dc3593a9 |
| 2 | rest_days | z_vs_league | - | +0.003882 | 0.0609 | 452 | 452.0 | 06aa3b4a6346834a |
| 3 | battersFaced | rank_in_league | - | +0.003913 | 0.0377 | 452 | 452.0 | fbc888e9789c3790 |
| 4 | rest_days | raw | - | +0.003943 | 0.0568 | 452 | 452.0 | 00a8a2a1bfe9da5b |
| 5 | is_b2b | z_vs_league | - | +0.003965 | 0.0615 | 452 | 401.7 | ed918c45504a341a |
| 6 | appearances_last_3d | rank_in_league | - | +0.004069 | 0.0360 | 452 | 447.7 | 342306b2e17d8097 |
| 7 | appearances_last_3d | raw | - | +0.004093 | 0.0282 | 452 | 440.3 | 014b67725914b823 |
| 8 | is_b2b | rank_in_league | - | +0.004251 | 0.0361 | 452 | 362.4 | 3e48dbea3f5da0a0 |
| 9 | rest_days | rank_in_league | - | +0.004327 | 0.0521 | 452 | 369.5 | 83c47721b7257c60 |
| 10 | battersFaced | raw | - | +0.004333 | 0.0199 | 452 | 452.0 | b8bf61622cd4e261 |
| 11 | appearances_last_3d | z_vs_league | - | +0.004397 | 0.0300 | 452 | 435.8 | 84d6b1775747951c |
| 12 | battersFaced | z_vs_league | - | +0.004657 | 0.0224 | 452 | 452.0 | a3e5b47615a92dba |
| 13 | rest_days | delta_vs_prior | - | +0.016459 | 0.0133 | 452 | 418.3 | 1b35f0fc2ad51d44 |
| 14 | rest_days | ew | {'halflife': 20} | +0.017076 | 0.0066 | 452 | 377.1 | 0e35ba35efbf7481 |
| 15 | rest_days | ew | {'halflife': 10} | +0.017114 | 0.0065 | 452 | 376.2 | 6116608ea7d5d9e6 |
| 16 | is_b2b | delta_vs_prior | - | +0.017190 | 0.0040 | 452 | 452.0 | d702b95888b6b8fd |
| 17 | rest_days | ew | {'halflife': 5} | +0.017195 | 0.0063 | 452 | 374.7 | 281f99cf97319bf7 |
| 18 | rest_days | ew | {'halflife': 3} | +0.017306 | 0.0060 | 452 | 373.3 | 94a49db3ac016277 |
| 19 | appearances_last_3d | delta_vs_prior | - | +0.017822 | 0.0071 | 452 | 355.7 | c886a2badfb66c9d |
| 20 | appearances_last_3d | ew | {'halflife': 20} | +0.020387 | 0.0027 | 452 | 380.6 | f22dddfd5f9b4e68 |

### mlb_gate (2026-W36)
| rank | feature | transform | params | delta (model - incumbent) | screen DM p | n | n_eff | hash |
|---|---|---|---|---|---|---|---|---|
| 1 | p_home_elo | rank_in_league | - | +0.003621 | 0.0775 | 452 | 341.1 | 20ec4b89eb68fba0 |
| 2 | p_base | rank_in_league | - | +0.003621 | 0.0775 | 452 | 341.1 | 3daf4b893fe3715f |
| 3 | p_home_elo | raw | - | +0.004438 | 0.0455 | 452 | 433.5 | 1a5c2af36be83005 |
| 4 | p_base | raw | - | +0.004438 | 0.0455 | 452 | 433.5 | 5204ddf10a3f2039 |
| 5 | p_home_elo | z_vs_league | - | +0.005523 | 0.0422 | 452 | 406.0 | 00fe9b94e5434470 |
| 6 | p_base | z_vs_league | - | +0.005523 | 0.0422 | 452 | 406.0 | 09e038facbd1be62 |
| 7 | p_home_elo | delta_vs_prior | - | +0.017775 | 0.0093 | 452 | 352.3 | 857216efce16b2f7 |
| 8 | p_base | delta_vs_prior | - | +0.017775 | 0.0093 | 452 | 352.3 | ac62facb7790f0df |
| 9 | p_base | ew | {'halflife': 3} | +0.019867 | 0.0060 | 452 | 371.6 | 1af403180ab37ce6 |
| 10 | p_home_elo | ew | {'halflife': 3} | +0.019867 | 0.0060 | 452 | 371.6 | dcf0554d2e0d6dac |
| 11 | p_home_elo | ew | {'halflife': 5} | +0.020078 | 0.0059 | 452 | 369.1 | 62d11c015bf7bf07 |
| 12 | p_base | ew | {'halflife': 5} | +0.020078 | 0.0059 | 452 | 369.1 | 6b957d3d3bd61ec7 |
| 13 | p_home_elo | ew | {'halflife': 10} | +0.020243 | 0.0058 | 452 | 366.8 | c91ad7ccc0321cb6 |
| 14 | p_base | ew | {'halflife': 10} | +0.020243 | 0.0058 | 452 | 366.8 | efef8dc93f97ac5d |
| 15 | p_home_elo | ew | {'halflife': 20} | +0.020316 | 0.0058 | 452 | 365.6 | b1ef09432bfe36e1 |
| 16 | p_base | ew | {'halflife': 20} | +0.020316 | 0.0058 | 452 | 365.6 | e75da921ee317476 |

### nba_boxdetail (2026-W36)
| rank | feature | transform | params | delta (model - incumbent) | screen DM p | n | n_eff | hash |
|---|---|---|---|---|---|---|---|---|
| 1 | fast_break_pts_diff_asof | rank_in_league | - | +0.001183 | 0.5480 | 499 | 499.0 | 753699a5f712dba2 |
| 2 | away_tov_pts_l10_asof | ew | {'halflife': 3} | +0.001240 | 0.3556 | 499 | 352.5 | d172e2584f49d2d5 |
| 3 | away_paint_pts_asof | raw | - | +0.001287 | 0.2071 | 499 | 460.2 | 132c1e901af65862 |
| 4 | away_tov_pts_l10_asof | ew | {'halflife': 5} | +0.001355 | 0.3046 | 499 | 355.5 | 8df1c1c4ae10ae91 |
| 5 | away_paint_pts_l10_asof | raw | - | +0.001392 | 0.1826 | 499 | 434.5 | 06a7c1fe64e1e3b8 |
| 6 | tov_pts_l10_diff_asof | ew | {'halflife': 20} | +0.001406 | 0.4019 | 499 | 381.6 | 7843d4a57318840d |
| 7 | largest_lead_diff_asof | ew | {'halflife': 20} | +0.001407 | 0.2803 | 499 | 467.1 | 0338d0e7a79eeb49 |
| 8 | away_fast_break_pts_asof | raw | - | +0.001412 | 0.1750 | 499 | 499.0 | 418bb2d4da360592 |
| 9 | away_foul_trouble_l10_asof | raw | - | +0.001418 | 0.3261 | 499 | 499.0 | e5b99abbee35a993 |
| 10 | tov_pts_l10_diff_asof | ew | {'halflife': 10} | +0.001420 | 0.4019 | 499 | 371.3 | 57c65301baf388a0 |
| 11 | foul_trouble_diff_asof | raw | - | +0.001436 | 0.2248 | 499 | 499.0 | 8732a2e0050e688c |
| 12 | away_tov_pts_l10_asof | ew | {'halflife': 10} | +0.001440 | 0.2690 | 499 | 360.0 | 80dfb8be584293e6 |
| 13 | tov_pts_diff_asof | ew | {'halflife': 20} | +0.001441 | 0.3652 | 499 | 435.3 | 0272e3289e896e62 |
| 14 | foul_trouble_l10_diff_asof | raw | - | +0.001442 | 0.2600 | 499 | 499.0 | 1f58ca53e4d9c66d |
| 15 | home_largest_lead_asof | ew | {'halflife': 20} | +0.001443 | 0.3502 | 499 | 432.3 | 0f1638e4f5d99da2 |
| 16 | largest_lead_diff_asof | ew | {'halflife': 10} | +0.001446 | 0.2637 | 499 | 469.4 | 887ee07cdf71ef2c |
| 17 | tov_pts_l10_diff_asof | ew | {'halflife': 5} | +0.001451 | 0.3992 | 499 | 356.3 | 8eb48e634a89fc03 |
| 18 | tov_pts_diff_asof | ew | {'halflife': 10} | +0.001455 | 0.3619 | 499 | 424.9 | b8cd8a771ccd76be |
| 19 | away_tov_pts_l10_asof | ew | {'halflife': 20} | +0.001481 | 0.2529 | 499 | 362.9 | b8a6e58863bf04aa |
| 20 | home_largest_lead_asof | ew | {'halflife': 10} | +0.001483 | 0.3340 | 499 | 432.0 | bb6bc91c89559f5b |

### nba_carryover (2026-W36)
| rank | feature | transform | params | delta (model - incumbent) | screen DM p | n | n_eff | hash |
|---|---|---|---|---|---|---|---|---|
| 1 | away_rest_days_asof | ew | {'halflife': 20} | +0.001444 | 0.3741 | 499 | 399.1 | 77d25d53afb16a84 |
| 2 | rest_days_diff_asof | ew | {'halflife': 3} | +0.001466 | 0.2972 | 499 | 384.1 | 45be24ea41dfdaf9 |
| 3 | away_rest_days_asof | ew | {'halflife': 10} | +0.001476 | 0.3555 | 499 | 399.6 | ee487322019bf542 |
| 4 | rest_days_diff_asof | ew | {'halflife': 5} | +0.001508 | 0.2835 | 499 | 404.2 | ef61a0ead6b3bbb8 |
| 5 | away_rest_days_asof | ew | {'halflife': 5} | +0.001519 | 0.3263 | 499 | 400.0 | 889f53ee0f2f7f58 |
| 6 | away_rest_days_asof | ew | {'halflife': 3} | +0.001549 | 0.2980 | 499 | 401.2 | 21c10cb2944ea4d1 |
| 7 | rest_days_diff_asof | ew | {'halflife': 10} | +0.001558 | 0.2689 | 499 | 419.9 | a4a76e29a1add6fe |
| 8 | rest_days_diff_asof | ew | {'halflife': 20} | +0.001589 | 0.2611 | 499 | 427.1 | e7fa27b1950cfa4a |
| 9 | away_heavy_min_load_asof | ew | {'halflife': 20} | +0.001673 | 0.2037 | 499 | 368.6 | 9e22c0e945d12195 |
| 10 | away_heavy_min_load_asof | ew | {'halflife': 10} | +0.001709 | 0.1976 | 499 | 365.9 | 553692d75b372fb8 |
| 11 | home_heavy_min_load_asof | ew | {'halflife': 20} | +0.001753 | 0.2236 | 499 | 368.3 | 3dbd01a37730e5db |
| 12 | home_rest_days_asof | ew | {'halflife': 3} | +0.001755 | 0.1871 | 499 | 389.7 | 77c846ff32862697 |
| 13 | away_heavy_min_load_asof | ew | {'halflife': 5} | +0.001759 | 0.1927 | 499 | 360.0 | 9aa16123efcb981d |
| 14 | home_heavy_min_load_asof | ew | {'halflife': 10} | +0.001772 | 0.2208 | 499 | 368.0 | 777982676e814dc6 |
| 15 | away_heavy_min_load_asof | ew | {'halflife': 3} | +0.001776 | 0.2001 | 499 | 351.6 | 397543b58671b404 |
| 16 | heavy_min_load_diff_asof | ew | {'halflife': 20} | +0.001780 | 0.2091 | 499 | 349.2 | ffa3675665240aaa |
| 17 | home_heavy_min_load_asof | ew | {'halflife': 5} | +0.001800 | 0.2191 | 499 | 367.7 | 42af0954f9fd2590 |
| 18 | home_rest_days_asof | ew | {'halflife': 5} | +0.001801 | 0.1755 | 499 | 385.1 | 861251ab20ce9a20 |
| 19 | home_heavy_min_load_asof | ew | {'halflife': 3} | +0.001814 | 0.2237 | 499 | 367.4 | 5e968760528b78c9 |
| 20 | home_rest_days_asof | ew | {'halflife': 10} | +0.001837 | 0.1673 | 499 | 383.7 | d7fce6e53ac4ccda |

### nba_defender_rollup (2026-W36)
| rank | feature | transform | params | delta (model - incumbent) | screen DM p | n | n_eff | hash |
|---|---|---|---|---|---|---|---|---|
| 1 | away_def_matchup_min_asof | ew | {'halflife': 5} | +0.001399 | 0.3403 | 499 | 436.0 | 7c2d9c18e4789296 |
| 2 | away_def_matchup_min_asof | ew | {'halflife': 10} | +0.001405 | 0.3386 | 499 | 437.6 | 7764c709c94c46dd |
| 3 | def_switches_per_game_diff_asof | ew | {'halflife': 20} | +0.001416 | 0.2897 | 499 | 375.5 | 16e36d3abc1df896 |
| 4 | away_def_switches_per_game_asof | ew | {'halflife': 10} | +0.001416 | 0.2897 | 499 | 375.5 | 1745a69cd0486f99 |
| 5 | home_def_switches_per_game_asof | ew | {'halflife': 20} | +0.001416 | 0.2897 | 499 | 375.5 | 339f7fbc915561a1 |
| 6 | def_switches_per_game_diff_asof | ew | {'halflife': 5} | +0.001416 | 0.2897 | 499 | 375.5 | 7a0dae56783c5f47 |
| 7 | away_def_switches_per_game_asof | ew | {'halflife': 3} | +0.001416 | 0.2897 | 499 | 375.5 | 80e5833e4d660cc2 |
| 8 | home_def_switches_per_game_asof | ew | {'halflife': 5} | +0.001416 | 0.2897 | 499 | 375.5 | 80fdc00d0337e89e |
| 9 | home_def_switches_per_game_asof | ew | {'halflife': 3} | +0.001416 | 0.2897 | 499 | 375.5 | 84051d3311bec811 |
| 10 | away_def_switches_per_game_asof | ew | {'halflife': 20} | +0.001416 | 0.2897 | 499 | 375.5 | 8aaaf5d7f688111a |
| 11 | def_switches_per_game_diff_asof | ew | {'halflife': 10} | +0.001416 | 0.2897 | 499 | 375.5 | c9a275fffa9a2a29 |
| 12 | away_def_switches_per_game_asof | ew | {'halflife': 5} | +0.001416 | 0.2897 | 499 | 375.5 | eef3ddf45a3b3cdd |
| 13 | def_switches_per_game_diff_asof | ew | {'halflife': 3} | +0.001416 | 0.2897 | 499 | 375.5 | f26c3f9370440a01 |
| 14 | home_def_switches_per_game_asof | ew | {'halflife': 10} | +0.001416 | 0.2897 | 499 | 375.5 | fb0df6e57a879657 |
| 15 | away_def_matchup_min_asof | ew | {'halflife': 20} | +0.001423 | 0.3335 | 499 | 438.1 | a1406ff90b0572cd |
| 16 | away_def_matchup_min_asof | ew | {'halflife': 3} | +0.001435 | 0.3291 | 499 | 433.5 | bdcbbc178f83f2a7 |
| 17 | away_def_pts_allowed_per36_asof | ew | {'halflife': 3} | +0.001547 | 0.1925 | 499 | 499.0 | a545ec90661b68d6 |
| 18 | away_def_pts_allowed_per36_asof | ew | {'halflife': 5} | +0.001588 | 0.1866 | 499 | 499.0 | b698938aa4993416 |
| 19 | away_def_pts_allowed_per36_asof | ew | {'halflife': 10} | +0.001615 | 0.1869 | 499 | 499.0 | 166280640d31a7c7 |
| 20 | away_def_pts_allowed_per36_asof | ew | {'halflife': 20} | +0.001627 | 0.1882 | 499 | 499.0 | 0754c3e7080bca6f |

### nba_gate (2026-W36)
| rank | feature | transform | params | delta (model - incumbent) | screen DM p | n | n_eff | hash |
|---|---|---|---|---|---|---|---|---|
| 1 | pace_diff_asof | ew | {'halflife': 10} | -0.000263 | 0.8730 | 499 | 349.3 | 0704bb6a5ad03559 |
| 2 | pace_diff_asof | ew | {'halflife': 20} | -0.000259 | 0.8748 | 499 | 355.4 | 951ad286b957639b |
| 3 | pace_diff_asof | ew | {'halflife': 5} | -0.000229 | 0.8890 | 499 | 341.4 | ecb2fd0d540ffcfe |
| 4 | pace_diff_asof | ew | {'halflife': 3} | -0.000120 | 0.9415 | 499 | 337.6 | 85b0101fb9436446 |
| 5 | oreb_pg_diff_asof | ew | {'halflife': 3} | +0.000047 | 0.9715 | 499 | 463.6 | 59fb248e8391bde7 |
| 6 | oreb_pg_diff_asof | ew | {'halflife': 5} | +0.000078 | 0.9542 | 499 | 458.5 | dde0fb143dd2d925 |
| 7 | oreb_pg_diff_asof | ew | {'halflife': 10} | +0.000128 | 0.9264 | 499 | 458.1 | 7965465abc76270e |
| 8 | oreb_pg_diff_asof | ew | {'halflife': 20} | +0.000162 | 0.9080 | 499 | 459.3 | d5be508f1e421200 |
| 9 | stl_x_fg3m_asof | ew | {'halflife': 20} | +0.000431 | 0.7817 | 499 | 353.6 | d586644e25b0b5c2 |
| 10 | stl_x_fg3m_asof | ew | {'halflife': 10} | +0.000542 | 0.7272 | 499 | 354.8 | 866cfe71736806bd |
| 11 | stl_x_fg3m_asof | ew | {'halflife': 5} | +0.000757 | 0.6249 | 499 | 358.2 | 36d47a910a5e2357 |
| 12 | p_elo | raw | - | +0.000902 | 0.5064 | 499 | 499.0 | ae9250f510397fa8 |
| 13 | p_base | raw | - | +0.000902 | 0.5064 | 499 | 499.0 | e2d5332bf229493e |
| 14 | oreb_pg_diff_asof | raw | - | +0.000936 | 0.4018 | 499 | 425.4 | c330144137a55af6 |
| 15 | fg3m_diff_asof | ew | {'halflife': 3} | +0.000994 | 0.4584 | 499 | 451.2 | 1d62556555b8c0c9 |
| 16 | stl_x_fg3m_asof | ew | {'halflife': 3} | +0.001004 | 0.5156 | 499 | 363.6 | cb844747322d6c33 |
| 17 | fg3m_diff_asof | ew | {'halflife': 5} | +0.001018 | 0.4507 | 499 | 443.8 | e6f607cc3af05ffe |
| 18 | fg3m_diff_asof | ew | {'halflife': 10} | +0.001034 | 0.4467 | 499 | 439.5 | 670d823c50d8ac7c |
| 19 | fg3m_diff_asof | ew | {'halflife': 20} | +0.001041 | 0.4452 | 499 | 437.9 | 0a40fe4df45cd7fe |
| 20 | pace_diff_asof | raw | - | +0.001047 | 0.3172 | 499 | 379.2 | 62ebb655151e7451 |

### nba_opp_allowed (2026-W36)
| rank | feature | transform | params | delta (model - incumbent) | screen DM p | n | n_eff | hash |
|---|---|---|---|---|---|---|---|---|
| 1 | n_games_asof | raw | - | -0.000640 | 0.7338 | 499 | 452.0 | 906036db6e7e8480 |
| 2 | opp_fg3m_allowed_vs_league | rank_in_league | - | +0.000353 | 0.7625 | 499 | 499.0 | 8aaca2a20a75a189 |
| 3 | opp_fg3m_allowed_asof | rank_in_league | - | +0.000414 | 0.7153 | 499 | 499.0 | 41472b0d3464573f |
| 4 | n_games_asof | z_vs_league | - | +0.000679 | 0.7069 | 499 | 451.2 | 71b7b0020f47a4c4 |
| 5 | opp_fg3m_allowed_vs_league | raw | - | +0.000724 | 0.5033 | 499 | 499.0 | aea4b3ce84c9b81d |
| 6 | opp_fg3m_allowed_asof | raw | - | +0.000735 | 0.4986 | 499 | 499.0 | f003ce7dedbedf5d |
| 7 | opp_reb_allowed_asof | rank_in_league | - | +0.000873 | 0.4581 | 499 | 499.0 | 3fbdbb1e0a57cb28 |
| 8 | opp_reb_allowed_vs_league | rank_in_league | - | +0.000903 | 0.4340 | 499 | 499.0 | 08656c18f47107a5 |
| 9 | opp_ast_allowed_vs_league | rank_in_league | - | +0.001243 | 0.3225 | 499 | 499.0 | 9486952eeb3377c9 |
| 10 | opp_reb_allowed_asof | ew | {'halflife': 3} | +0.001272 | 0.4164 | 499 | 479.2 | b4ec9b2b6d93fcb2 |
| 11 | opp_pts_allowed_vs_league | rank_in_league | - | +0.001275 | 0.2064 | 499 | 499.0 | f235fc9fccdc0bce |
| 12 | opp_reb_allowed_vs_league | ew | {'halflife': 3} | +0.001289 | 0.4110 | 499 | 478.8 | 3dbd5b6f9d5b18f6 |
| 13 | opp_ast_allowed_asof | rank_in_league | - | +0.001303 | 0.2902 | 499 | 499.0 | d72a076626414239 |
| 14 | opp_pts_allowed_asof | rank_in_league | - | +0.001314 | 0.2029 | 499 | 499.0 | 111bb37516fbd491 |
| 15 | opp_blk_allowed_vs_league | delta_vs_prior | - | +0.001387 | 0.3811 | 499 | 449.7 | 0e2190761fe8421d |
| 16 | opp_blk_allowed_asof | delta_vs_prior | - | +0.001390 | 0.3806 | 499 | 451.2 | ea13b95cf791d0c9 |
| 17 | opp_reb_allowed_asof | ew | {'halflife': 5} | +0.001481 | 0.3407 | 499 | 485.5 | 8b71dde570e0424b |
| 18 | opp_reb_allowed_vs_league | ew | {'halflife': 5} | +0.001498 | 0.3361 | 499 | 485.3 | 0374133d0ef33a0f |
| 19 | opp_tov_allowed_asof | delta_vs_prior | - | +0.001599 | 0.2438 | 499 | 412.0 | 5ad110ca11bf482e |
| 20 | opp_tov_allowed_vs_league | delta_vs_prior | - | +0.001601 | 0.2418 | 499 | 412.1 | 1a424d877bcd904a |

### nba_player_adv (2026-W36)
| rank | feature | transform | params | delta (model - incumbent) | screen DM p | n | n_eff | hash |
|---|---|---|---|---|---|---|---|---|
| 1 | offensiverating_asof | raw | - | +0.000167 | 0.9440 | 499 | 499.0 | 002f7c90b8d88e76 |
| 2 | offensiverating_asof | z_vs_league | - | +0.001105 | 0.6016 | 499 | 499.0 | a763dbdf954cb0ad |
| 3 | usagepercentage_asof | ew | {'halflife': 20} | +0.001355 | 0.3432 | 499 | 499.0 | 0948d670ca8f60ff |
| 4 | usagepercentage_asof | ew | {'halflife': 10} | +0.001372 | 0.3342 | 499 | 499.0 | a9ea9c0bee02895e |
| 5 | usagepercentage_asof | ew | {'halflife': 5} | +0.001415 | 0.3153 | 499 | 499.0 | fc203ac8c7562450 |
| 6 | usagepercentage_asof | ew | {'halflife': 3} | +0.001472 | 0.2933 | 499 | 499.0 | 42d0b1a45bc88a96 |
| 7 | offensiverating_asof | ew | {'halflife': 3} | +0.001498 | 0.5488 | 499 | 358.3 | 2e38f17ef60e08b2 |
| 8 | defensiverating_asof | ew | {'halflife': 20} | +0.001552 | 0.2739 | 499 | 405.5 | 8e9e5529eba016b5 |
| 9 | defensiverating_asof | ew | {'halflife': 10} | +0.001564 | 0.2687 | 499 | 405.3 | 8ef617b4f71cd259 |
| 10 | offensiverating_asof | ew | {'halflife': 5} | +0.001571 | 0.5259 | 499 | 364.2 | cbfadad19f951510 |
| 11 | defensiverating_asof | ew | {'halflife': 5} | +0.001593 | 0.2571 | 499 | 406.1 | 9046cb941b2c9e4c |
| 12 | possessions_asof | rank_in_league | - | +0.001593 | 0.2178 | 499 | 325.5 | 07b5733d409d98a5 |
| 13 | defensiverating_asof | ew | {'halflife': 3} | +0.001633 | 0.2408 | 499 | 409.2 | 35d042ae15fdbee2 |
| 14 | offensiverating_asof | ew | {'halflife': 10} | +0.001657 | 0.5017 | 499 | 368.8 | f7cb30e426db8cf5 |
| 15 | offensiverating_asof | ew | {'halflife': 20} | +0.001707 | 0.4880 | 499 | 371.1 | 8bb9c1004b4d9313 |
| 16 | offensiverating_asof | rank_in_league | - | +0.001715 | 0.2432 | 499 | 499.0 | ccfeb47bb6aabd1f |
| 17 | defensiverating_asof | delta_vs_prior | - | +0.001825 | 0.1527 | 499 | 499.0 | 928d7bd0fd23bf40 |
| 18 | defensiverating_asof | rank_in_league | - | +0.001857 | 0.1208 | 499 | 499.0 | 10d3b0754a339aea |
| 19 | defensiverating_asof | raw | - | +0.002018 | 0.0838 | 499 | 341.1 | a093b8664519b25d |
| 20 | n_prior | ew | {'halflife': 3} | +0.002027 | 0.2040 | 499 | 346.3 | 3286eaf49ad3f98e |

### nba_player_value_features (2026-W36)
| rank | feature | transform | params | delta (model - incumbent) | screen DM p | n | n_eff | hash |
|---|---|---|---|---|---|---|---|---|
| 1 | continuity | raw | - | -0.000178 | 0.8899 | 499 | 373.9 | e4101cdd583c3d30 |
| 2 | continuity | rank_in_league | - | +0.000113 | 0.9273 | 499 | 430.0 | 1bc2d97234a1a667 |
| 3 | star_absence_delta | ew | {'halflife': 3} | +0.000652 | 0.7688 | 499 | 400.8 | d67c883d9128d441 |
| 4 | star_absence_delta | ew | {'halflife': 5} | +0.000723 | 0.7315 | 499 | 417.5 | 5369ad06801a0e09 |
| 5 | continuity | z_vs_league | - | +0.000727 | 0.6018 | 499 | 321.9 | 0d733002328bcd9c |
| 6 | star_absence_delta | ew | {'halflife': 10} | +0.000802 | 0.6878 | 499 | 443.4 | 6311976f82484745 |
| 7 | star_absence_delta | ew | {'halflife': 20} | +0.000857 | 0.6580 | 499 | 461.6 | fc4246da9ae80281 |
| 8 | roster_value_asof | rank_in_league | - | +0.001328 | 0.4383 | 499 | 395.0 | 445d5f16aff64ba6 |
| 9 | continuity | ew | {'halflife': 20} | +0.001622 | 0.4518 | 499 | 464.9 | f964bfebed763476 |
| 10 | top_heavy | raw | - | +0.001688 | 0.1014 | 499 | 393.3 | 9c117a22c5c641f4 |
| 11 | continuity | ew | {'halflife': 10} | +0.001730 | 0.4153 | 499 | 473.4 | 9b3b37d81f592236 |
| 12 | top_heavy | ew | {'halflife': 20} | +0.001756 | 0.2016 | 499 | 384.1 | 8205969be7e3c398 |
| 13 | top_heavy | ew | {'halflife': 10} | +0.001771 | 0.1993 | 499 | 382.0 | d13b702bd4669850 |
| 14 | top_heavy | ew | {'halflife': 5} | +0.001808 | 0.1937 | 499 | 377.5 | fb1d72b9431d4784 |
| 15 | top_heavy | ew | {'halflife': 3} | +0.001868 | 0.1849 | 499 | 371.3 | 158949e8c86fca71 |
| 16 | continuity | ew | {'halflife': 5} | +0.001943 | 0.3486 | 499 | 487.7 | 5ca8c06e8f5bb082 |
| 17 | top_heavy | z_vs_league | - | +0.001968 | 0.0483 | 499 | 401.0 | ab77b32396eecf66 |
| 18 | roster_value_asof | ew | {'halflife': 20} | +0.002052 | 0.1987 | 499 | 340.4 | e6f26a5c99c2746b |
| 19 | roster_value_asof | ew | {'halflife': 10} | +0.002069 | 0.1944 | 499 | 341.3 | d1684819df42348a |
| 20 | roster_value_asof | ew | {'halflife': 5} | +0.002120 | 0.1816 | 499 | 344.0 | 026e691ea705b824 |

### nba_quarter_shape (2026-W36)
| rank | feature | transform | params | delta (model - incumbent) | screen DM p | n | n_eff | hash |
|---|---|---|---|---|---|---|---|---|
| 1 | away_q4_margin_asof | ew | {'halflife': 20} | +0.000506 | 0.7672 | 499 | 499.0 | 6b5e7e623fc0eedf |
| 2 | away_q4_margin_asof | ew | {'halflife': 10} | +0.000540 | 0.7449 | 499 | 499.0 | b07cff9cc503f7c7 |
| 3 | away_q4_margin_asof | ew | {'halflife': 5} | +0.000699 | 0.6583 | 499 | 499.0 | bbda5fc9f15a1a00 |
| 4 | home_quarter_volatility_asof | delta_vs_prior | - | +0.000748 | 0.6024 | 499 | 374.0 | 98879fdb358ac2dd |
| 5 | away_quarter_volatility_asof | ew | {'halflife': 3} | +0.000829 | 0.5800 | 499 | 335.9 | 8930b72be9dd2725 |
| 6 | away_quarter_volatility_asof | ew | {'halflife': 5} | +0.000872 | 0.5708 | 499 | 333.4 | 3ce935f971022a2d |
| 7 | away_quarter_volatility_asof | ew | {'halflife': 10} | +0.000931 | 0.5544 | 499 | 333.7 | d7e93d04f4a05335 |
| 8 | diff_quarter_volatility_asof | ew | {'halflife': 20} | +0.000957 | 0.5166 | 499 | 404.3 | 268ffbffe77e8469 |
| 9 | diff_quarter_volatility_asof | ew | {'halflife': 10} | +0.000967 | 0.5100 | 499 | 404.5 | 86d5534da0c345e3 |
| 10 | away_quarter_volatility_asof | ew | {'halflife': 20} | +0.000968 | 0.5442 | 499 | 334.5 | 270ac19baa808ad2 |
| 11 | home_first_half_margin_asof | delta_vs_prior | - | +0.000981 | 0.5126 | 499 | 499.0 | c877a0addc08fd6f |
| 12 | diff_quarter_volatility_asof | ew | {'halflife': 5} | +0.000995 | 0.4946 | 499 | 405.8 | 80cc198a76123f98 |
| 13 | away_q4_margin_asof | ew | {'halflife': 3} | +0.001027 | 0.4969 | 499 | 499.0 | 638c272dd98d9989 |
| 14 | diff_quarter_volatility_asof | ew | {'halflife': 3} | +0.001048 | 0.4703 | 499 | 408.8 | 3315b73f45bf8270 |
| 15 | diff_q1_margin_asof | raw | - | +0.001154 | 0.3282 | 499 | 342.1 | 46028ee4a342a470 |
| 16 | home_second_half_margin_asof | ratio_to_opponent | - | +0.001177 | 0.2259 | 499 | 499.0 | 575f758661887341 |
| 17 | diff_first_half_margin_asof | raw | - | +0.001352 | 0.1824 | 499 | 363.1 | 39756d148ffff496 |
| 18 | home_quarter_volatility_asof | ew | {'halflife': 20} | +0.001410 | 0.3181 | 499 | 353.8 | 774e8bc03dbb1579 |
| 19 | home_quarter_volatility_asof | ew | {'halflife': 10} | +0.001414 | 0.3152 | 499 | 355.0 | f5ed1137567d26ad |
| 20 | home_quarter_volatility_asof | ew | {'halflife': 5} | +0.001423 | 0.3103 | 499 | 357.1 | 8c1ad861f314a2e2 |

### nba_team_adv (2026-W36)
| rank | feature | transform | params | delta (model - incumbent) | screen DM p | n | n_eff | hash |
|---|---|---|---|---|---|---|---|---|
| 1 | pace_diff_asof | ew | {'halflife': 10} | -0.000263 | 0.8730 | 499 | 349.3 | 0704bb6a5ad03559 |
| 2 | pace_diff_asof | ew | {'halflife': 20} | -0.000259 | 0.8748 | 499 | 355.4 | 951ad286b957639b |
| 3 | pace_diff_asof | ew | {'halflife': 5} | -0.000229 | 0.8890 | 499 | 341.4 | ecb2fd0d540ffcfe |
| 4 | pace_diff_asof | ew | {'halflife': 3} | -0.000120 | 0.9415 | 499 | 337.6 | 85b0101fb9436446 |
| 5 | pace_diff_asof | raw | - | +0.001047 | 0.3172 | 499 | 379.2 | 62ebb655151e7451 |
| 6 | away_pace_asof | ew | {'halflife': 3} | +0.001175 | 0.3965 | 499 | 374.1 | 2eb8d03f1ff0944d |
| 7 | away_pace_asof | ew | {'halflife': 5} | +0.001276 | 0.3563 | 499 | 364.7 | 3ba7498ee1e4db93 |
| 8 | away_pace_asof | ew | {'halflife': 10} | +0.001354 | 0.3251 | 499 | 363.8 | 47b9c914d6af551e |
| 9 | pace_diff_asof | rank_in_league | - | +0.001362 | 0.3377 | 499 | 356.5 | 704c2d54918d85d2 |
| 10 | away_pace_asof | ew | {'halflife': 20} | +0.001392 | 0.3100 | 499 | 365.0 | a6595a8a1d6743f6 |
| 11 | home_pace_asof | ew | {'halflife': 20} | +0.001491 | 0.3835 | 499 | 396.5 | bcf4361353605ab4 |
| 12 | home_pace_asof | ew | {'halflife': 10} | +0.001503 | 0.3805 | 499 | 396.1 | d0eeab52ee629ad9 |
| 13 | home_pace_asof | ew | {'halflife': 5} | +0.001524 | 0.3753 | 499 | 395.3 | 22fba3d1136c4901 |
| 14 | pace_diff_asof | z_vs_league | - | +0.001539 | 0.1837 | 499 | 393.4 | 7343dfe583200c12 |
| 15 | home_pace_asof | ew | {'halflife': 3} | +0.001547 | 0.3699 | 499 | 394.3 | f3033734803ed4d2 |
| 16 | away_def_rtg_asof | ew | {'halflife': 10} | +0.001565 | 0.2572 | 499 | 359.3 | 6e42761d6e859818 |
| 17 | away_def_rtg_asof | ew | {'halflife': 5} | +0.001569 | 0.2507 | 499 | 364.8 | d3ca9cff2dbc09fd |
| 18 | away_def_rtg_asof | ew | {'halflife': 20} | +0.001572 | 0.2577 | 499 | 357.1 | 662738ea7f49b782 |
| 19 | away_oreb_pct_asof | ew | {'halflife': 20} | +0.001588 | 0.2199 | 499 | 382.4 | c1d44e7896bc5b40 |
| 20 | away_def_rtg_asof | ew | {'halflife': 3} | +0.001596 | 0.2357 | 499 | 373.6 | d42d8e34b2b4a5af |
