"""Generic mechanism -> trigger wiring for the NBA mechanism ledger.

One declared row per CONFIRMED/REPLICATED mechanism section. A row either names
a persisted, leak-free as-of column (the trigger) or states, in data terms, why
no trigger exists locally (NOT_TESTABLE -- a wired state, not a gap).

DESCRIPTIVE_ONLY. No edge or ROI claim is made anywhere in this module.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
DOMAIN = "data/domains/basketball_nba"
GAMES = DOMAIN + "/games.parquet"
# Frozen local corpus (games x odds inner join) shared with signals/foundry_run.py.
CORPUS_START, CORPUS_END = "2025-10-21", "2026-04-12"
# A trial on a mostly-absent column is a base-rate trial wearing the column's
# name; below this share of the frozen corpus the row stays NOT_TESTABLE.
MIN_COVERAGE = 0.25


def _t(slug: str, source: str, expr: str, threshold: float) -> tuple:
    return slug, {"source": source, "expr": expr, "threshold": threshold}


def _n(slug: str, reason: str) -> tuple:
    return slug, {"source": None, "expr": None, "reason": reason}


# slug -> trigger definition. Slugs are mechanism_exposure.slugify() outputs.
WIRING: dict[str, dict] = dict([
    _n("stint_continuity_x_defensive_rebound_rate",
       "stint-grain continuity_s exists only in the possession/stint corpus; no "
       "game-grain as-of continuity column is persisted under data/domains/basketball_nba"),
    _n("lineup_spacing_x_transition_frequency",
       "lineup spacing composite is persisted only as data/cache/atlas_player_spacing_gravity"
       ".parquet (979 player-season rows, season-final aggregate) -- wrong grain and not as-of"),
    _n("lineup_spacing_x_late_clock_7s_efficiency",
       "same spacing ingredient as the transition-frequency row: season-final player aggregate, "
       "no game-grain as-of column"),
    _n("lineup_synergy_talent_differential_h3_on_off_talent_diff",
       "on/off talent differential is persisted only as data/cache/atlas_team_lineup_synergy"
       ".parquet (30 team-season rows) -- a season-final aggregate, unusable as an as-of feature"),
    _t("endq1_x_star_minutes_load_partial", DOMAIN + "/carryover_asof.parquet",
       "heavy_min_load_diff_asof", 70.0),
    _n("12_attr_lineup_quality_composite_partial_pregame_confirmed_in_game_conditioning_null",
       "the 12-attribute lineup composite is built in memory by the prereg lineup-composition "
       "run; no composite column is persisted at game grain"),
    _n("spacing_x_clutch_5pt_5min",
       "requires both the season-final spacing aggregate and a live clutch (<=5pt, <=5min) "
       "state; neither is a persisted game-grain as-of column"),
    _t("back_to_back_b2b_rest_penalty", GAMES, "home_b2b - away_b2b", 1.0),
    _t("home_court_advantage_magnitude", GAMES, "1", 0.0),
    _n("garbage_time_bench_production_inflation",
       "trigger is a live in-game abs(margin)>=20 state; the frozen corpus scores pregame "
       "home-win only and no as-of column encodes a live margin"),
    _n("clutch_usage_compression_confirmed_but_reversed_direction_amplification_not_compression",
       "overall_fga_share is a player-game quantity; no team-game as-of usage-share column "
       "is persisted, and the outcome is a player prop, not the corpus home-win label"),
    _n("rotation_size_persists_coach_rotation_pattern_stability",
       "no avg_rotation_size as-of column exists on disk; it is derivable from "
       "player_boxscores.parquet but has never been built as an as-of feature"),
    _n("clutch_lineup_shortening",
       "trigger is a live close-and-late clutch state (expected clutch rotation size); "
       "no pregame as-of column encodes it"),
    _n("usage_redistribution_persistence_after_a_high_usage_player_is_out",
       "trigger is a pregame-known player absence; no injury/availability as-of column "
       "is persisted under data/domains/basketball_nba"),
    _n("transition_frequency_pace_mismatch_distinct_from_overall_pace_variance_22",
       "the as-of trailing transition-rate differential is computed in memory by "
       "validate_transition_frequency.py from data/cache/team_system/pbp; no game-grain "
       "parquet column persists it (pace_asof is a different, REJECTED mechanism, #22)"),
    _n("second_unit_bench_lineup_continuity_effect_confirmed_reversed_direction_vs_full_lineup_1",
       "bench-stint continuity is a stint-grain quantity, the same absence as the "
       "full-lineup continuity row"),
    _t("fast_break_points_persistence_margin_relation", DOMAIN + "/boxdetail_asof.parquet",
       "fast_break_pts_diff_asof", 3.0),
    _t("points_in_the_paint_persistence_margin_relation", DOMAIN + "/boxdetail_asof.parquet",
       "paint_pts_diff_asof", 5.5),
    _t("q1_slow_start_tendency_persistence", DOMAIN + "/asof_quarter_shape.parquet",
       "diff_q1_margin_asof", 3.0),
    _t("on_ball_defensive_matchup_skill_is_a_stable_predictively_valid_trait",
       DOMAIN + "/asof_defender_rollup.parquet", "def_fg_pct_allowed_diff_asof", 0.034),
    _t("team_assist_rate_persistence_margin_relation_box_detail_family_design_new_column",
       DOMAIN + "/asof_features_ext.parquet", "ast_rate_diff_asof", 0.057),
    _t("largest_lead_persistence_margin_relation_4th_box_detail_row_extends_the_34_35_36_"
       "triple_pass_to_the_previously_untested_largest_lead_column_already_named_as_unlocked_"
       "in_the_family_header_above", DOMAIN + "/boxdetail_asof.parquet",
       "largest_lead_diff_asof", 4.5),
    _n("timeout_interrupts_opponent_scoring_run_raw_pre_post_gap_not_a_causal_claim",
       "trigger is an in-game timeout event with a pre/post scoring window; no game-grain "
       "as-of column encodes timeout usage"),
    _n("blowout_margin_threshold_effect_on_starter_minutes_allocation_final_margin_proxy_for_"
       "live_win_probability_garbage_time_detection",
       "the outcome is starter-minutes allocation conditioned on the REALIZED final margin; "
       "the frozen corpus scores pregame home-win only and final margin is not an as-of input"),
    _n("q1_lead_extension_beyond_a_naive_ar_1_model_in_the_q2_that_follows_sim2_p2_m6_bucket_target",
       "trigger is a live abs(q1_margin)>=15 in-game state feeding a Q2 margin transition; the "
       "frozen corpus has no in-game states and asof_quarter_shape holds trailing averages only"),
    _n("per_game_whistle_tightness_disperses_beyond_a_team_adjusted_poisson_null_identity_free_"
       "mirrors_mlb_39",
       "the claim is a dispersion property of realized per-game foul counts, not a pregame "
       "predictor; no crew-assignment or officiating as-of input exists locally "
       "(data/cache/officials/ does not exist)"),
    _n("between_game_starting_lineup_continuity_roster_stability_streak_vs_point_differential",
       "the opening-lineup continuity streak is rebuilt in memory by validate_research_wave5.py; "
       "no as-of streak column is persisted at game grain"),
])

TESTABLE = tuple(slug for slug, row in WIRING.items() if row["expr"])
_CACHE: dict[str, dict[str, float]] = {}


def corpus_game_ids(root: Path = REPO_ROOT) -> dict[str, str]:
    """Return {game_id: date} for the frozen corpus window (outcome-free)."""
    frame = pd.read_parquet(root / GAMES, columns=["game_id", "date"])
    frame["date"] = pd.to_datetime(frame["date"], utc=True).dt.date.astype(str)
    frame = frame[(frame.date >= CORPUS_START) & (frame.date <= CORPUS_END)]
    return {str(g): str(d) for g, d in zip(frame.game_id, frame.date)}


def value_table(slug: str, root: Path = REPO_ROOT) -> dict[str, float]:
    """Build {game_id: trigger value} for one wired mechanism, outcomes excluded."""
    row = WIRING[slug]
    if not row["expr"]:
        raise KeyError("mechanism has no trigger column: " + slug)
    if slug in _CACHE:
        return _CACHE[slug]
    # ponytail: the guard, not the ceremony -- an outcome column inside a trigger
    # expression is the one way this table could leak into a scored trial.
    for banned in ("home_win", "away_win", "outcome", "margin_final"):
        assert banned not in row["expr"], "trigger expression reads an outcome: " + slug
    frame = pd.read_parquet(root / row["source"])
    if row["expr"].replace(".", "", 1).isdigit():  # constant trigger (always live)
        raw = pd.Series(float(row["expr"]), index=frame.index)
    else:
        raw = pd.Series(frame.eval(row["expr"]), index=frame.index)
    values = pd.to_numeric(raw, errors="coerce")
    table = {str(g): float(v) for g, v in zip(frame["game_id"], values) if pd.notna(v)}
    _CACHE[slug] = table
    return table


def coverage(slug: str, root: Path = REPO_ROOT) -> dict:
    """Measure how much of the frozen corpus this trigger actually covers."""
    ids = corpus_game_ids(root)
    table = value_table(slug, root)
    covered = {g: d for g, d in ids.items() if g in table}
    return {"n_corpus": len(ids), "n_covered": len(covered),
            "share": round(len(covered) / len(ids), 4) if ids else 0.0,
            "as_of": max(covered.values()) if covered else None}


def matchup_index(root: Path = REPO_ROOT) -> dict[tuple, str]:
    """Map (date, home_team, away_team) -> games.parquet game_id."""
    frame = pd.read_parquet(root / GAMES, columns=["game_id", "date", "home_team", "away_team"])
    frame["date"] = pd.to_datetime(frame["date"], utc=True).dt.date.astype(str)
    return {(str(d), str(h), str(a)): str(g) for g, d, h, a in
            zip(frame.game_id, frame.date, frame.home_team, frame.away_team)}


def column_exposures(game_ids: list[str], root: Path = REPO_ROOT) -> dict[str, list[dict]]:
    """Per-game trigger evidence for every column-wired mechanism (descriptive)."""
    out: dict[str, list[dict]] = {game: [] for game in game_ids}
    for slug in TESTABLE:
        row = WIRING[slug]
        table = value_table(slug, root)
        for game in game_ids:
            value = table.get(game)
            if value is None or abs(value) < row["threshold"]:
                continue
            out[game].append({"slug": slug, "trigger_evidence": {
                "name": row["expr"], "value": round(value, 6),
                "threshold": row["threshold"], "source_artifact": row["source"]}})
    return out


def rollup(slugs: list[str]) -> dict:
    """Split a mechanism list into wired-with-trigger / wired-NOT_TESTABLE / unwired."""
    return {"wired_trigger": [s for s in slugs if WIRING.get(s, {}).get("expr")],
            "wired_not_testable": [s for s in slugs if s in WIRING and not WIRING[s]["expr"]],
            "not_wired": [s for s in slugs if s not in WIRING]}
