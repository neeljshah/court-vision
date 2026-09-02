"""Declared SOCCER mechanism -> trigger wiring rows (DATA module).

Same contract as ``mechanism_wiring.WIRING`` and ``mechanism_wiring_mlb.WIRING``:
one row per CONFIRMED/REPLICATED section of ``domains/soccer/knowledge/
mechanisms.md``. A row either names a persisted, leak-free as-of column that
lives in the scored corpus, or states in data terms why no such column exists.

Measured corpus facts behind every reason below (2026-09-03, this repo):

- The scored soccer corpus is ``data/cache/combo/gate_corpus_soccer.parquet``
  (25,834 rows, 2015-08-07..2026-05-24, six league ``corpus_unit``s
  E0/E1/D1/F1/I1/SP1) joined to the devigged decimal close by
  ``scripts/platformkit/eval_gate/close_join.py`` (16,322 states with a close,
  vintage SYNTHETIC per S34).
- Its feature columns are ``p_base``, ``p_over25``, the ten pregame shot/SOT
  as-of columns it has always carried (``home_sot_for_l10``, ``away_sot_for_l10``,
  ``diff_sot_for_asof``, ``diff_sot_against_asof``, ``diff_shots_for_asof``,
  ``diff_shots_against_asof``, ``home_sot_ratio_for_asof``,
  ``away_sot_ratio_for_asof``, ``home_n_prior``, ``away_n_prior``) and, since
  gap **S53**, seventeen more as-of columns joined on ``event_id``: the eight
  remaining ``asof_features`` per-side shot/SOT columns and the nine-column
  as-of xG-PROXY family from ``data/domains/soccer/asof_xg_proxy.parquet``
  (``diff_xg_supremacy_asof`` among them, 25,708 / 25,834 non-null).
- Its outcome ``y`` is the OVER-2.5-total-goals indicator (mean 0.5154) and the
  close is the devigged over/under 2.5 pair -- not a match-result label.
- Fourteen of the fifteen CONFIRMED soccer mechanisms need an ingredient that is
  StatsBomb event-grain (score state, possession id, shot type, PPDA, goal-kick
  height, tactical shift), or lives on ``data/domains/soccer_intl/results.parquet``
  (neutral venue, competition type). None of those is a column of the scored
  corpus, and the soccer_intl frame shares **0** of its 49,477 rows with the
  25,834 corpus matches on (date, home_team, away_team) -- so those three rows
  cannot be joined even in principle.
- The fifteenth (trailing xG supremacy) names an xG as-of column, which S53
  joined onto the spine; it is the one row here that now carries a trigger.

DESCRIPTIVE_ONLY; no dollar or ROI claim anywhere. A trigger row declares a
column, not a result -- verdicts come from ``mechanism_close_effect.py`` and are
descriptive local effects, never claims.
"""
from __future__ import annotations

CORPUS = ("data/cache/combo/gate_corpus_soccer.parquet x close_join, "
          "16322 states 2019-08-02..2026-05-24, outcome = over 2.5 goals")
GATE = "data/cache/combo/gate_corpus_soccer.parquet"

# (slug, reason). Slugs are mechanism_exposure.slugify() outputs and must match
# the CONFIRMED/REPLICATED section titles exactly -- an approximate slug is inert.
ROWS: tuple[tuple[str, str], ...] = (
    ("team_time_score_state_conditioned_shot_model_replicated_null_vs_naive_baseline",
     "the ingredient is a live (team, time-bucket, score-bucket) cell from the StatsBomb event "
     "cache; " + GATE + " has no score_state or time_bucket column -- its eleven feature columns "
     "are pregame shot/SOT as-of aggregates. The section's own ledger status is a REPLICATED "
     "NULL; it parses as wired here only because the status string contains 'REPLICATED'"),
    ("first_goal_timing_predicts_final_result",
     "the trigger is the in-match first-goal event and the outcome is the match result; " + GATE +
     " carries no first_goal column, holds no in-match states, and its scored label is the "
     "over-2.5-total-goals indicator, not a result label"),
    ("leading_team_defensive_shell_game_state_shot_suppression",
     "the trigger is a live leading-versus-tied score state at StatsBomb event grain and the "
     "outcome is shots per minute; " + GATE + " has no score-state column and no shot-rate "
     "outcome, only pregame as-of shot/SOT differentials"),
    ("set_piece_vs_open_play_shot_conversion",
     "the ingredient is shot-grain shot.type.name (Corner / Free Kick versus Open Play); no "
     "set-piece share column exists in " + GATE + " -- diff_shots_for_asof and diff_sot_for_asof "
     "pool every shot type and cannot be split by origin"),
    ("pressing_intensity_ppda_proxy_vs_opponent_turnover_rate",
     "the PPDA proxy (opponent passes divided by own Pressure+Duel+Interception count) is an "
     "event-grain quantity recomputed in memory by validate_pressing_defense.py; no ppda column "
     "is persisted in " + GATE + " and the outcome is an opponent turnover rate, not the "
     "corpus over-2.5 label"),
    ("goalkeeper_distribution_style_vs_possession_retention",
     "the trigger is goal-kick pass height at StatsBomb event grain and the outcome is possession "
     "retention on that pass; " + GATE + " carries no goal_kick or distribution column and scores "
     "a pregame match-total label"),
    ("formation_change_mid_match_impact",
     "the trigger is an in-match Tactical Shift event with pre/post shot-rate windows; " + GATE +
     " carries no tactical_shift column and holds no in-match states"),
    ("home_advantage_magnitude_collapses_at_neutral_venues",
     "the trigger is a neutral_venue flag measured on data/domains/soccer_intl/results.parquet "
     "(49,425 played matches, 1872-2026); " + GATE + " is six domestic league corpus_units with "
     "no neutral column, and none of those international matches is a corpus row"),
    ("neutral_venue_split_replicates_across_era_split_half_stability",
     "the same neutral_venue ingredient as the row above, split by era on the soccer_intl corpus; "
     + GATE + " carries no neutral column and does not contain those matches, so neither the "
     "trigger nor the era split can be built at corpus grain"),
    ("tournament_competitive_context_lifts_the_scoring_environment_vs_friendlies",
     "the trigger is a competitive-versus-friendly competition label on "
     "data/domains/soccer_intl/results.parquet; " + GATE + " holds only the six domestic league "
     "corpus_units (E0, E1, D1, F1, I1, SP1) and carries no competition-type column, so the "
     "friendly arm of the contrast does not exist in it at all"),
    ("trailing_xg_supremacy_is_a_stable_team_trait_persistence_not_incremental_brier",
     "SUPERSEDED by the TRIGGERS entry below: S53 joined the as-of xG-PROXY family onto "
     + GATE + ", so diff_xg_supremacy_asof is now a column of the scored corpus"),
    ("first_substitution_timing_early_vs_late_moderates_the_shot_rate_shift",
     "the trigger is the in-match minute of a team's first substitution and the outcome is a "
     "shots-per-minute shift around it; " + GATE + " carries no substitution column and holds no "
     "in-match windows"),
    ("trailing_team_shot_rate_vs_tied_extends_9_s_leading_tied_state_machine_to_the_previously_"
     "discarded_trailing_case",
     "the trigger is a live trailing-versus-tied score state, the same absence as the "
     "leading/tied row; " + GATE + " has no score-state column and no shots-per-minute outcome"),
    ("xg_additivity_breaks_down_in_same_team_shot_rebound_clusters_multi_shot_possessions_"
     "overstate_combined_scoring_probability",
     "the unit is a within-match possession id carrying per-shot statsbomb_xg; " + GATE + " is "
     "match-grain with neither a possession nor an xG column, and the claim is a calibration "
     "property of summed shot xG rather than a pregame trigger on the match label"),
    ("defensive_block_depth_predicts_a_team_s_own_counterattack_shot_share_distinct_outcome_from_"
     "the_closed_26_opponent_shot_quality_null",
     "the predictor is an event-grain compactness proxy (own defensive-action mean x minus own "
     "shot mean x) and the outcome is the play_pattern=='From Counter' share of a team's own "
     "shots; neither exists as a column in " + GATE),
)

# The rows whose declared ingredient IS a column of the enriched spine (S53).
# Same shape as mechanism_wiring_tennis's ``_t`` rows; overrides the ROWS reason
# for that slug while leaving every other row's declared absence untouched.
TRIGGERS: dict[str, dict] = {
    "trailing_xg_supremacy_is_a_stable_team_trait_persistence_not_incremental_brier": {
        "source": GATE, "expr": "diff_xg_supremacy_asof",
        "columns": ("diff_xg_supremacy_asof",), "mask": None,
        "note": "the mechanism's own ingredient is the as-of xG-supremacy differential from "
                "domains.soccer.asof_xg_proxy (a SHOTS-BASED PROXY, not true xG), joined onto "
                + GATE + " by S53 on event_id at 25,708 / 25,834 non-null. The ledger's claim is "
                "a SPLIT-HALF PERSISTENCE property of the trait, so the corpus-grain rendering "
                "here is the trait level itself against the close residual -- a declared "
                "rendering of the ingredient, NOT the ledger's persistence statistic"},
}

WIRING: dict[str, dict] = {
    slug: TRIGGERS.get(slug) or {"source": None, "expr": None, "reason": reason}
    for slug, reason in ROWS}

# A duplicate slug would silently drop a mechanism from the ledger join.
assert len(WIRING) == len(ROWS), "duplicate soccer mechanism slug in ROWS"
