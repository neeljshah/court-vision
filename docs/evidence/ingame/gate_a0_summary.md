# Gate A-0: in-game score vs market (overall)

| sport | n_ticks | n_games | date_range | brier_model | brier_market | brier_delta | brier_CI95 | logloss_delta | logloss_CI95 | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| mlb_clean | 78986 | 227 | 2026-06-20..2026-07-12 | 0.23768 | 0.20665 | 0.03103 | [0.01704, 0.04535] | 0.10624 | [0.06777, 0.14831] | BEHIND |
| soccer_intl | 9003 | 51 | 2026-06-22..2026-07-12 | 0.22789 | 0.14273 | 0.08516 | [0.04876, 0.12696] | 0.40488 | [0.25445, 0.58057] | BEHIND |

## mlb_clean: by phase (Brier delta, model-market)
| phase | n_ticks | n_games | brier_delta | CI95 | verdict |
|---|---|---|---|---|---|
| 1-3 | 19900 | 173 | 0.01812 | [0.00420, 0.03097] | BEHIND |
| 4-6 | 18765 | 178 | 0.02874 | [0.00915, 0.04837] | BEHIND |
| 7-9+ | 13981 | 171 | 0.07411 | [0.03667, 0.10990] | BEHIND |

## mlb_clean: by market_prob band
| band | n_ticks | n_games | brier_delta | CI95 | verdict |
|---|---|---|---|---|---|
| <0.2 | 8003 | 121 | 0.01875 | [0.00507, 0.03255] | BEHIND |
| 0.2-0.4 | 7785 | 153 | 0.04069 | [0.01425, 0.07129] | BEHIND |
| 0.4-0.6 | 41337 | 220 | 0.04718 | [0.02292, 0.07174] | BEHIND |
| 0.6-0.8 | 12707 | 172 | -0.00701 | [-0.03581, 0.02223] | UNDERPOWERED |
| >0.8 | 9154 | 125 | 0.01344 | [-0.00450, 0.02766] | UNDERPOWERED |

## mlb_clean: by minutes_to_close
| bucket | n_ticks | n_games | brier_delta | CI95 | verdict |
|---|---|---|---|---|---|
| >60 | 59562 | 220 | 0.03866 | [0.02063, 0.05805] | BEHIND |
| 30-60 | 9534 | 220 | 0.00867 | [-0.00234, 0.01960] | UNDERPOWERED |
| 10-30 | 6484 | 221 | 0.00675 | [-0.00388, 0.01734] | UNDERPOWERED |
| 3-10 | 2269 | 213 | 0.00786 | [-0.00243, 0.01946] | UNDERPOWERED |
| <3 | 1137 | 227 | 0.00352 | [-0.00618, 0.01411] | UNDERPOWERED |

## mlb_clean: tick change-rate
| n_with_prev | model_changed_frac | market_changed_frac | state_changed_frac |
|---|---|---|---|
| 78759 | 0.082873068474714 | 0.25019362866466055 | 0.5575362815678209 |

## soccer_intl: by phase (Brier delta, model-market)
| phase | n_ticks | n_games | brier_delta | CI95 | verdict |
|---|---|---|---|---|---|
| 0-30 | 1336 | 27 | 0.12418 | [0.05513, 0.19478] | UNDERPOWERED |
| 31-60 | 1453 | 28 | 0.11650 | [0.04391, 0.19747] | UNDERPOWERED |
| 61-90+ | 869 | 24 | 0.14620 | [0.06858, 0.22278] | UNDERPOWERED |

## soccer_intl: by market_prob band
| band | n_ticks | n_games | brier_delta | CI95 | verdict |
|---|---|---|---|---|---|
| <0.2 | 2607 | 35 | 0.02981 | [0.01770, 0.04629] | BEHIND |
| 0.2-0.4 | 2445 | 33 | 0.09508 | [0.04596, 0.15460] | BEHIND |
| 0.4-0.6 | 1344 | 24 | 0.22002 | [0.10895, 0.32730] | UNDERPOWERED |
| 0.6-0.8 | 1343 | 24 | 0.10474 | [0.02658, 0.18987] | UNDERPOWERED |
| >0.8 | 1264 | 21 | 0.01593 | [-0.01112, 0.04875] | UNDERPOWERED |

## soccer_intl: by minutes_to_close
| bucket | n_ticks | n_games | brier_delta | CI95 | verdict |
|---|---|---|---|---|---|
| >60 | 3484 | 46 | 0.09026 | [0.04491, 0.14708] | BEHIND |
| 30-60 | 2681 | 48 | 0.08037 | [0.04532, 0.12594] | BEHIND |
| 10-30 | 1830 | 49 | 0.08538 | [0.04497, 0.13111] | BEHIND |
| 3-10 | 663 | 51 | 0.09012 | [0.05059, 0.13608] | BEHIND |
| <3 | 345 | 51 | 0.06021 | [0.02583, 0.09899] | BEHIND |

## soccer_intl: tick change-rate
| n_with_prev | model_changed_frac | market_changed_frac | state_changed_frac |
|---|---|---|---|
| 8952 | 0.36371760500446826 | 0.3694146559428061 | 0.20676943699731903 |
