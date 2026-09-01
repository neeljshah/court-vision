"""Declared MLB mechanism -> trigger wiring rows (DATA module).

Same contract as ``mechanism_wiring.WIRING``: one row per CONFIRMED/REPLICATED
section of ``domains/mlb/knowledge/mechanisms.md``. A row either names a
persisted, leak-free as-of column or states, in data terms, why no trigger
exists locally.

Measured corpus facts behind every reason below (2026-09-01, this repo):

- The frozen MLB corpus is ``data/domains/mlb/games.parquet`` x ``odds.parquet``,
  27,983 games, 2010-04-04..2021-11-02.
- Every persisted mechanism-ingredient artifact is 2022 or later:
  ``platoon_split_index`` / ``umpire_zone_index`` / ``catcher_framing_index``
  (season ``2022_2023``), ``sp_velo_states`` (2022-2023), ``bullpen_relief_chains``
  (2022-2026), ``umpire_assignments`` (2026-07-09..2026-07-16), statcast
  ``savant_full__2023..2026`` and ``statcast_fuller__2022/2023``,
  ``carryover_asof__2023/2024``. None of them joins the frozen corpus window.
- The only game-grain as-of columns that DO join it are
  ``asof_features.sp_ra_diff_asof`` (94.91% of games) and
  ``asof_inning.early_rate_diff_asof`` / ``late_rate_diff_asof`` (99.93%);
  ``asof_park.parquet`` and ``asof_espn_box.parquet`` join 0 corpus games.
  No CONFIRMED MLB mechanism's own ingredient is one of those three columns.

Consequently every row here is NOT_TESTABLE. That is a wired state with a
measured data reason, not a gap. DESCRIPTIVE_ONLY; no edge or ROI claim.
"""
from __future__ import annotations

CORPUS = "data/domains/mlb/games.parquet x odds.parquet, 2010-04-04..2021-11-02, 27983 games"

# (slug, reason). Slugs are mechanism_exposure.slugify() outputs and must match
# the CONFIRMED section titles exactly -- an approximate slug would be inert.
ROWS: tuple[tuple[str, str], ...] = (
    ("platoon_pitcher_hand_x_batter_stand_x_pitch_type",
     "the claim is a PA-grain pitcher-hand x batter-stand x pitch-type interaction; the only "
     "persisted platoon artifact is data/domains/mlb/platoon_split_index.parquet (394 batter "
     "rows at season='2022_2023' grain) -- a season-final aggregate outside the frozen corpus window"),
    ("count_leverage_ahead_behind_x_pitch_mix",
     "count state and pitch mix are pitch-grain quantities recomputed in memory by "
     "domains/mlb/pitch_engine/selection.py over statcast; no game-grain as-of column is "
     "persisted and local statcast starts at 2022, after the frozen corpus ends"),
    ("base_out_state_x_contact_type_gb_fb",
     "base-out state x batted-ball type is a PA-grain run-value quantity; the only base-out "
     "corpus on disk is data/cache/ingame/mlb_atbat_states__2022/2023.parquet, disjoint from "
     "the frozen 2010-2021 corpus, and no game-grain as-of column encodes it"),
    ("edge_zone_widening_in_two_strike_counts",
     "edge-zone (Statcast zone 11-14) rate by count is a pitch-grain quantity recomputed by "
     "domains/mlb/knowledge/validate_count_zone.py; no persisted as-of column exists and no "
     "local pitch corpus predates 2022"),
    ("two_strike_chase_rate_rise",
     "swing-and-out-of-zone rate at two strikes is the same pitch-grain quantity as the "
     "edge-zone row, with the same absence: recomputed in memory, never persisted as a "
     "game-grain as-of column"),
    ("first_pitch_strike_suppresses_walk_rate",
     "the conditioning and the outcome are both within-PA (first-pitch strike -> walk); the "
     "frozen corpus scores pregame home-win only and no as-of column encodes first-pitch "
     "strike rate"),
    ("contact_quality_persistence_split_half",
     "split-half repeatability of mean launch_speed is a batter-level property of the statcast "
     "corpus (2022+); it is not a game-grain as-of team column and cannot be evaluated on the "
     "2010-2021 frozen corpus"),
    ("ground_ball_double_play_suppression",
     "the claim conditions on batted-ball type inside a force state; no game-grain as-of column "
     "encodes it, and realized double plays exist locally only in "
     "data/domains/mlb/espn_boxscores.parquet (2 rows)"),
    ("times_through_order_decay_raw_velo_independent",
     "times-through-order is a PA-grain axis; the nearest persisted as-of starter quantity in "
     "the frozen window is sp_first6_diff_ew (data/cache/combo/gate_corpus_mlb.parquet, 87.63% "
     "of era_2010_2021 rows), a first-six-innings run differential with no TTO axis -- a "
     "different quantity, not this mechanism's ingredient"),
    ("walk_economy_baserunner_inflation",
     "run expectancy per walk by base state is a PA-grain quantity built in memory by "
     "domains/mlb/re24_table.py; no as-of column persists it and the outcome is run expectancy, "
     "not the corpus home-win label"),
    ("big_inning_generation_run_clustering",
     "home_big_inning_share / away_big_inning_share exist only in "
     "data/domains/mlb/postmortem.parquet, a REALIZED post-game artifact; asof_inning.parquet "
     "persists early/late scoring RATES as-of and carries no leadoff-gating or run-clustering column"),
    ("pitch_count_efficiency_and_starter_durability",
     "pitches per PA is a pitch-grain quantity; the persisted as-of pitch-count column "
     "sp_prior_pitch_count_diff_asof lives only in carryover_asof__2023.parquet and "
     "carryover_asof__2024.parquet (seasons 2023-2024), disjoint from the frozen 2010-2021 corpus"),
    ("high_leverage_strand_prevention",
     "strand rate under RISP is a reliever-grain quantity; data/domains/mlb/bullpen_relief_chains"
     ".parquet (2022-2026) carries rest-day and appearance counts only, no strand column, and its "
     "window does not intersect the frozen corpus"),
    ("spin_rate_deception_independent_of_velocity",
     "release spin rate is a pitch-grain statcast column (data/cache/statcast/savant_full__2023"
     "..2026.parquet); no persisted game-grain as-of team column carries it and the corpus window "
     "predates local statcast"),
    ("launch_angle_sweet_spot_consistency",
     "sweet-spot rate is a batter-level repeatability property of the statcast corpus (2022+); "
     "no game-grain as-of column persists it and the outcome is a batter skill, not the corpus "
     "home-win label"),
    ("called_strike_rate_dispersion_exceeds_binomial_noise",
     "the claim is a dispersion property of REALIZED per-game called-strike rates, not a pregame "
     "predictor (same status as the NBA whistle-tightness row); no as-of column exists and no "
     "local pitch corpus predates 2022"),
    ("umpire_called_strike_zone_size_varies_by_count_state_compassionate_umpire",
     "the axis is the pitch count state; umpire identity is persisted only in umpire_assignments"
     ".parquet (248 rows, 2026-07-09..2026-07-16) and umpire_zone_index.parquet (102 umpire rows, "
     "season='2022_2023'), neither of which joins the frozen 2010-2021 corpus"),
    ("catcher_framing_multi_season_trend_decline_curve_proxy_no_local_age_column",
     "catcher_framing_index.parquet holds 113 catcher rows at season='2022_2023' grain and no "
     "game-grain catcher assignment column exists; the trend is a multi-season aggregate outside "
     "the frozen corpus window"),
    ("mid_inning_pitching_change_interrupts_the_batting_team_s_scoring_rate_raw_pre_post_gap_"
     "same_design_family_as_the_confirmed_nba_47_timeout_interrupt_row",
     "the trigger is an in-game mid-inning pitcher change with pre/post PA windows; the frozen "
     "corpus scores pregame home-win only and no as-of column encodes pitching changes"),
    ("pinch_hitter_substitutions_skew_toward_securing_the_platoon_opposite_hand_advantage_"
     "against_the_current_pitcher",
     "the trigger is an in-game substitution observed at PA grain; no as-of column encodes "
     "substitutions and the outcome is the substitute's hand matchup, not the corpus home-win label"),
    ("per_game_2_strike_putaway_whiff_rate_disperses_beyond_binomial_noise_identity_free_mirrors_39",
     "identity-free dispersion of REALIZED per-game putaway-whiff rates, the same design as the "
     "called-strike dispersion row: a property of realized rates, not a pregame predictor, and no "
     "as-of column exists"),
    ("automatic_runner_zombie_runner_extra_inning_home_away_scoring_rate_parity_check_rule_era_aware",
     "the trigger is an inning==10 automatic-runner half-inning state under a rule era starting "
     "in 2020; the frozen corpus holds no in-game states and the outcome is a half-inning scoring "
     "rate, not the corpus home-win label"),
)

WIRING: dict[str, dict] = {slug: {"source": None, "expr": None, "reason": reason}
                           for slug, reason in ROWS}

# A duplicate slug would silently drop a mechanism from the ledger join.
assert len(WIRING) == len(ROWS), "duplicate MLB mechanism slug in ROWS"
