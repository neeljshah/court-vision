"""
v3_game_features.py — v3 game-level feature builder.

Extends v2 win_probability/game_models features with 6 new modules:
  - referee crew features (7 keys via referee_features.get_ref_crew_features)
  - news / injury features (9 keys via news_features.build_news_features)
  - schedule pressure for home + away (12 keys × 2 = 24 keys)
  - team form for home + away (7 keys × 2 = 14 keys)
  - coach features (22 keys via coach_features.get_coach_features)
  - ELO v2 (3 keys: home, away, diff — already in v2 but surfaced consistently)

Total v3 additions: ~75 new keys on top of v2's ~77 ≈ 150-160 total.

Public API
----------
    build_v3_game_features(home_team, away_team, home_team_id, away_team_id,
                           game_date, season, game_id) -> dict
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Optional

log = logging.getLogger(__name__)

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_DIR)

# ── Safe defaults for each module ────────────────────────────────────────────

_REF_DEFAULTS: dict = {
    "ref_crew_game_total_avg": 0.0,
    "ref_crew_pace_avg":       0.0,
    "ref_crew_fta_avg":        0.0,
    "ref_crew_pf_avg":         0.0,
    "ref_crew_home_win_pct":   0.0,
    "ref_crew_games_avg":      0.0,
    "ref_crew_known":          0,
}

_NEWS_DEFAULTS: dict = {
    "home_inactives_count":     0,
    "away_inactives_count":     0,
    "home_questionable_count":  0,
    "away_questionable_count":  0,
    "home_starter_change_flag": 0,
    "away_starter_change_flag": 0,
    "home_star_out_flag":       0,
    "away_star_out_flag":       0,
    "news_freshness_minutes":   999,
}

def _sched_defaults(prefix: str) -> dict:
    return {
        f"{prefix}_games_in_last_7d":           0,
        f"{prefix}_games_in_last_14d":          0,
        f"{prefix}_miles_traveled_last_7d":     0.0,
        f"{prefix}_miles_traveled_last_14d":    0.0,
        f"{prefix}_time_zones_crossed_last_7d": 0,
        f"{prefix}_consecutive_road_games":     0,
        f"{prefix}_consecutive_home_games":     0,
        f"{prefix}_days_since_last_game":       99,
        f"{prefix}_days_until_next_game":       99,
        f"{prefix}_is_4in6":                    0,
        f"{prefix}_is_5in7":                    0,
        f"{prefix}_cross_country_flag":         0,
    }

def _form_defaults(prefix: str, window: int = 10) -> dict:
    suf = f"l{window}"
    return {
        f"{prefix}_quality_of_wins_{suf}":       0.0,
        f"{prefix}_strength_of_schedule_{suf}":  0.0,
        f"{prefix}_clutch_record_{suf}":         0.5,
        f"{prefix}_3pt_variance_{suf}":          0.0,
        f"{prefix}_blowout_factor_{suf}":        0.2,
        f"{prefix}_avg_minutes_starters_{suf}":  30.0,
        f"{prefix}_win_pct_{suf}":               0.5,
    }

_COACH_DEFAULTS: dict = {
    "home_coach_avg_pace":            95.0,
    "home_coach_avg_oe":              110.0,
    "home_coach_avg_de":              112.0,
    "home_coach_3pa_rate":            0.38,
    "home_coach_fta_rate":            0.26,
    "home_coach_to_pct":              0.14,
    "home_coach_rotation_depth_avg":  8.0,
    "home_coach_late_close_win_pct":  0.50,
    "home_coach_b2b_win_pct":         0.44,
    "home_coach_games_coached":       0,
    "away_coach_avg_pace":            95.0,
    "away_coach_avg_oe":              110.0,
    "away_coach_avg_de":              112.0,
    "away_coach_3pa_rate":            0.38,
    "away_coach_fta_rate":            0.26,
    "away_coach_to_pct":              0.14,
    "away_coach_rotation_depth_avg":  8.0,
    "away_coach_late_close_win_pct":  0.50,
    "away_coach_b2b_win_pct":         0.44,
    "away_coach_games_coached":       0,
    "home_coach_pace_diff":           0.0,
    "home_coach_3pa_diff":            0.0,
}

_ELO_DEFAULTS: dict = {
    "v3_home_elo_v2":  1500.0,
    "v3_away_elo_v2":  1500.0,
    "v3_elo_diff_v2":  0.0,
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _prefix_dict(d: dict, prefix: str, skip_keys: frozenset = frozenset()) -> dict:
    """Return a new dict with every key prefixed, skipping keys in skip_keys."""
    return {
        f"{prefix}_{k}" if k not in skip_keys else k: v
        for k, v in d.items()
    }


def _build_schedule_features(team_id: int, game_date: str, season: str,
                              prefix: str) -> dict:
    try:
        from src.features.schedule_pressure import get_team_schedule_features
        raw = get_team_schedule_features(team_id, game_date, season)
        # Remap keys with prefix, drop meta keys
        skip = {"team_id", "game_date"}
        return {f"{prefix}_{k}": v for k, v in raw.items() if k not in skip}
    except Exception as exc:
        log.warning("schedule_pressure failed team_id=%d: %s", team_id, exc)
        return _sched_defaults(prefix)


def _build_form_features(team_abbrev: str, game_date: str, season: str,
                         prefix: str, window: int = 10) -> dict:
    try:
        from src.features.team_form import get_team_form_features
        raw = get_team_form_features(team_abbrev, game_date, season, window)
        skip = {"team_form_games", "team_abbrev"}
        # Strip the "team_" prefix from keys, add our prefix
        out = {}
        for k, v in raw.items():
            if k in skip:
                continue
            clean_k = k.replace("team_", "", 1)
            out[f"{prefix}_{clean_k}"] = v
        return out
    except Exception as exc:
        log.warning("team_form failed %s: %s", team_abbrev, exc)
        return _form_defaults(prefix, window)


# ── Main public API ────────────────────────────────────────────────────────────

def build_v3_game_features(
    home_team:    str,
    away_team:    str,
    home_team_id: int,
    away_team_id: int,
    game_date:    str,
    season:       str,
    game_id:      Optional[str] = None,
) -> dict:
    """
    Build the v3 game-level feature dict, extending v2 with new modules.

    All module calls are wrapped in try/except; on failure the module's safe
    defaults are returned so training is never blocked by a single missing source.

    Args:
        home_team:    Home team abbreviation (e.g. "LAL").
        away_team:    Away team abbreviation (e.g. "GSW").
        home_team_id: NBA numeric team ID for home team.
        away_team_id: NBA numeric team ID for away team.
        game_date:    ISO date string "YYYY-MM-DD".
        season:       Season string "YYYY-YY" (e.g. "2024-25").
        game_id:      NBA game ID string (for referee crew lookup). Optional.

    Returns:
        Flat dict suitable for a LightGBM feature row (~75 keys).
        Keys do NOT duplicate v2 FEATURE_COLS — only new keys are returned.
        Callers should merge with v2 features.
    """
    features: dict = {}

    # ── 1. Referee crew features ──────────────────────────────────────────────
    if game_id:
        try:
            from src.features.referee_features import get_ref_crew_features
            ref_feats = get_ref_crew_features(game_id, game_date or "")
            features.update(ref_feats)
        except Exception as exc:
            log.warning("referee_features failed game_id=%s: %s", game_id, exc)
            features.update(_REF_DEFAULTS)
    else:
        features.update(_REF_DEFAULTS)

    # ── 2. News / injury features ─────────────────────────────────────────────
    try:
        from src.data.news_features import build_news_features
        news_feats = build_news_features(home_team, away_team, game_date)
        features.update(news_feats)
    except Exception as exc:
        log.warning("news_features failed %s vs %s: %s", home_team, away_team, exc)
        features.update(_NEWS_DEFAULTS)

    # ── 3. Schedule pressure — home ───────────────────────────────────────────
    home_sched = _build_schedule_features(home_team_id, game_date, season, "home")
    features.update(home_sched)

    # ── 4. Schedule pressure — away ───────────────────────────────────────────
    away_sched = _build_schedule_features(away_team_id, game_date, season, "away")
    features.update(away_sched)

    # ── 5. Team form — home ───────────────────────────────────────────────────
    home_form = _build_form_features(home_team, game_date, season, "home")
    features.update(home_form)

    # ── 6. Team form — away ───────────────────────────────────────────────────
    away_form = _build_form_features(away_team, game_date, season, "away")
    features.update(away_form)

    # ── 7. Coach features ─────────────────────────────────────────────────────
    try:
        from src.features.coach_features import get_coach_features
        coach_feats = get_coach_features(home_team, away_team, season, game_date)
        # Drop string keys (coach names) — only keep numeric features
        features.update({
            k: v for k, v in coach_feats.items()
            if not isinstance(v, str)
        })
    except Exception as exc:
        log.warning("coach_features failed %s vs %s: %s", home_team, away_team, exc)
        features.update(_COACH_DEFAULTS)

    # ── 8. ELO v2 (consistent surface) ───────────────────────────────────────
    try:
        from src.features.elo import get_current_elo
        h_elo = get_current_elo(home_team)
        a_elo = get_current_elo(away_team)
        features["v3_home_elo_v2"] = round(h_elo, 2)
        features["v3_away_elo_v2"] = round(a_elo, 2)
        features["v3_elo_diff_v2"] = round(h_elo - a_elo, 2)
    except Exception as exc:
        log.warning("elo failed %s vs %s: %s", home_team, away_team, exc)
        features.update(_ELO_DEFAULTS)

    return features


# ── Feature column list for downstream trainers ────────────────────────────────

def get_v3_new_feature_cols(window: int = 10) -> list:
    """Return the list of new feature column names added by v3 (not in v2)."""
    suf = f"l{window}"
    cols = (
        list(_REF_DEFAULTS.keys())
        + list(_NEWS_DEFAULTS.keys())
        + list(_sched_defaults("home").keys())
        + list(_sched_defaults("away").keys())
        + [f"home_{k}" for k in _form_defaults("X", window) if k.startswith("X_")]
    )
    # Build programmatically from defaults
    ref_cols    = list(_REF_DEFAULTS.keys())
    news_cols   = list(_NEWS_DEFAULTS.keys())
    sched_h     = list(_sched_defaults("home").keys())
    sched_a     = list(_sched_defaults("away").keys())
    form_h      = list(_form_defaults("home", window).keys())
    form_a      = list(_form_defaults("away", window).keys())
    coach_cols  = list(_COACH_DEFAULTS.keys())
    elo_cols    = list(_ELO_DEFAULTS.keys())
    return (ref_cols + news_cols + sched_h + sched_a
            + form_h + form_a + coach_cols + elo_cols)
