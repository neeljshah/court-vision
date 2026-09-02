"""Declared TENNIS mechanism -> trigger wiring rows (DATA module).

Same contract as ``mechanism_wiring.WIRING`` and ``mechanism_wiring_mlb.WIRING``:
one row per CONFIRMED/REPLICATED section of ``domains/tennis/knowledge/
mechanisms.md``. A row either names persisted, leak-free as-of column(s) that
live in the scored corpus, or states in data terms why no such column exists.

Measured corpus facts behind every row below (2026-09-03, this repo):

- The scored tennis corpus is ``data/cache/combo/gate_corpus_tennis.parquet``
  (41,886 rows, 2015-01-04..2025-12-17, two ``corpus_unit``s -- ATP 30,616 and
  WTA 11,270, NEVER pooled) joined to the devigged decimal close by
  ``scripts/platformkit/eval_gate/close_join.py`` (33,685 states with a close,
  vintage SYNTHETIC per S34).
- Its ONLY feature columns are ``p_base``, ``p_elo``, ``surface``,
  ``p1_hold_pct_asof``, ``p2_hold_pct_asof``, ``diff_return_won_asof`` and
  ``diff_break_pct_asof``. Its outcome ``y`` is the p1-win indicator.
- Three CONFIRMED mechanisms have their own ingredient among those columns; the
  other twenty are point-grain, in-match, or need a column
  (hand, height, altitude, travel, round, seed, best_of, h2h, set detail,
  schedule density) that is not in the scored corpus.

DESCRIPTIVE_ONLY; no dollar or ROI claim anywhere. A trigger row here declares a
column, not a result -- verdicts come from
``mechanism_close_effect.py`` and are descriptive local effects, never claims.
"""
from __future__ import annotations

CORPUS = ("data/cache/combo/gate_corpus_tennis.parquet x close_join, "
          "33685 states 2015-01-04..2025-12-17, ATP + WTA kept separate")
GATE = "data/cache/combo/gate_corpus_tennis.parquet"


def _t(slug: str, expr: str, columns: tuple[str, ...], note: str,
       mask: str | None = None) -> tuple[str, dict]:
    return slug, {"source": GATE, "expr": expr, "columns": columns,
                  "mask": mask, "note": note}


def _n(slug: str, reason: str) -> tuple[str, dict]:
    return slug, {"source": None, "expr": None, "reason": reason}


ROWS: tuple[tuple[str, dict], ...] = (
    _t("serve_tier_x_return_tier_style_pairing_the_one_real_survivor",
       "(p1_hold_pct_asof - p2_hold_pct_asof) * diff_return_won_asof",
       ("p1_hold_pct_asof", "p2_hold_pct_asof", "diff_return_won_asof"),
       "the mechanism's ingredient is a serve-tier x return-tier PAIRING cell; the scored corpus "
       "carries the serve side per player (p1/p2_hold_pct_asof) and the return side as a "
       "differential (diff_return_won_asof), so the pairing is rendered at corpus grain as the "
       "product of the two as-of differentials -- a declared rendering of the interaction, not a "
       "per-player tercile cell"),
    _n("pressure_point_population_dip_break_game_set_tiebreak_deuce_confirmed",
       "the ingredient is a point-level score state (break / game / set / tiebreak / deuce) from "
       "data/cache/sackmann_pbp/slam_points.parquet; " + GATE + " is match-grain and carries no "
       "point-state column, and the claim's outcome is a per-point rate, not the p1-win label"),
    _t("serve_advantage_erodes_on_clay",
       "p1_hold_pct_asof - p2_hold_pct_asof",
       ("p1_hold_pct_asof", "p2_hold_pct_asof", "surface"),
       "the mechanism is a surface x serve-advantage interaction; both ingredients are corpus "
       "columns, so the trigger is the as-of serve-advantage differential MASKED to clay matches "
       "(surface is a native corpus column, 12,191 of 41,886 rows)",
       mask="surface == 'Clay'"),
    _n("serve_speed_decays_within_a_match",
       "the ingredient is per-point serve speed from the charting corpus, compared across an "
       "ordinal within-match point split; " + GATE + " holds no point rows and no serve-speed "
       "column, and the outcome is a within-match decay, not the p1-win label"),
    _n("double_fault_rate_falls_not_rises_by_set_3_local_null_of_the_fatigue_df_story",
       "the ingredient is a per-point double-fault indicator bucketed by set number; " + GATE +
       " carries neither a set-number nor a double-fault column. The section's own status is "
       "REJECTED; it parses as wired here only because the text contains CONFIRMED_LOCAL"),
    _n("right_handed_players_outperform_left_handed_opponents_rank_controlled_confirmed_folklore_"
       "reversing",
       "the trigger is player handedness from data/domains/tennis/players.parquet; " + GATE +
       " carries no hand column, so the right-versus-left contrast cannot be formed at corpus "
       "grain"),
    _n("recent_match_load_correlates_with_in_match_retirement",
       "the trigger is matches_last_7d from data/domains/tennis/schedule_density.parquet and the "
       "outcome is an in-match retirement; " + GATE + " carries no schedule-density column and "
       "its label is the p1-win indicator, not a retirement indicator"),
    _n("first_set_winner_wins_the_match_classic_population_claim_replicated_locally",
       "the trigger is the realized first-set winner, an in-match state; " + GATE + " holds only "
       "pregame as-of columns and no set-level state, so the conditioning event does not exist "
       "in it"),
    _n("momentum_streak_myth_last_set_game_win_predicts_next_point",
       "the ingredient is a point-to-point sequence within a service game from slam_points"
       ".parquet; " + GATE + " is match-grain with no point rows and no streak column"),
    _n("fatigue_from_prior_match_duration_minutes_not_just_count_local_null",
       "the trigger is prior-match duration in minutes; " + GATE + " carries no minutes or "
       "prior-match-duration as-of column -- the only load-shaped columns anywhere local are in "
       "schedule_density.parquet, which is not joined into the scored corpus"),
    _n("clay_grass_specialization_persistence",
       "the ingredient is a per-player surface-specific as-of win rate; " + GATE + " carries a "
       "native surface column but its as-of player columns (p1/p2_hold_pct_asof, "
       "diff_return_won_asof, diff_break_pct_asof) are surface-blind, so no specialization "
       "quantity exists at corpus grain and the claim is a split-half persistence property"),
    _n("deuce_game_length_effect_on_next_game_server_fatigue",
       "the ingredient is game-grain deuce length and the outcome is the next game's serve "
       "result; " + GATE + " holds neither game rows nor a deuce-length column"),
    _n("seed_ranking_upset_rate_by_round_confirmed_direction_opposite_the_seeded_claim",
       "the trigger is the tournament round crossed with seeding; " + GATE + " carries neither a "
       "round nor a seed column, so the by-round upset contrast cannot be formed"),
    _n("retirement_rate_by_round_and_surface_partial",
       "the trigger is round crossed with surface and the outcome is a retirement rate; " + GATE +
       " carries surface but no round column, and its label is the p1-win indicator rather than "
       "a retirement indicator"),
    _n("head_to_head_recency_bias_vs_current_ranking",
       "the trigger is a recency-weighted head-to-head record between the two players; " + GATE +
       " carries no head-to-head column and no ranking column -- p_elo is a rating built by the "
       "walk-forward Elo, a different quantity from the ranking this claim controls for"),
    _n("height_advantage_on_serve_surface_interacted",
       "the trigger is player height from data/domains/tennis/players.parquet (ATP-only); "
       + GATE + " carries no height column, so the height x surface interaction cannot be formed "
       "at corpus grain"),
    _n("break_point_conversion_rate_by_set_number",
       "the ingredient is a break-point conversion rate bucketed by set number; " + GATE +
       " carries diff_break_pct_asof as a single pregame differential and no set-number axis, so "
       "the by-set contrast this claim rests on does not exist in it"),
    _n("best_of_5_vs_best_of_3_upset_rate_difference",
       "the trigger is the match format (best-of-5 versus best-of-3); " + GATE + " carries no "
       "best_of column, and its two corpus_units are tours (ATP / WTA), not formats"),
    _n("altitude_effect_on_serve_ace_rate_confirmed_folklore_reversing",
       "the trigger is venue altitude from data/domains/tennis/travel_scouting.parquet (100 "
       "percent ATP event_ids) and the outcome is a combined ace rate; " + GATE + " carries "
       "neither an altitude nor an ace-rate column"),
    _n("long_travel_lowers_win_probability_net_of_ranking_confirmed",
       "the trigger is travel_diff_1000mi from travel_scouting.parquet; " + GATE + " carries no "
       "travel column, so the effect cannot be measured net of ranking at corpus grain"),
    _t("break_point_save_differential_predicts_outcome_controlling_for_serve_differential_"
       "confirmed_modest_relative_magnitude",
       "diff_break_pct_asof", ("diff_break_pct_asof",),
       "the mechanism's own ingredient is a pregame break-point differential and "
       "diff_break_pct_asof is exactly that column at corpus grain, as-of and leak-free"),
    _n("set_margin_dominance_metric_predicts_outcome_beyond_ranking_gap",
       "the ingredient is avg_games_per_set_asof_diff from data/domains/tennis/asof_setdetail"
       ".parquet; that column is not carried into " + GATE + ", whose as-of family is hold, "
       "return and break-point percentages only"),
    _n("new_ball_cycle_position_predicts_serve_execution_ace_rate_serve_speed_mixed_ace_rate_"
       "local_null_serve_speed_confirmed_but_reversed",
       "the trigger is a within-match cumulative game index mapped to a ball-age cycle and the "
       "outcome is ace rate or serve speed; " + GATE + " holds no point or game rows and none of "
       "those three quantities"),
)

WIRING: dict[str, dict] = dict(ROWS)

# A duplicate slug would silently drop a mechanism from the ledger join.
assert len(WIRING) == len(ROWS), "duplicate tennis mechanism slug in ROWS"
