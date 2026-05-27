"""src/prediction/quarter_feature_helper.py — inject quarter_features into inplay feature dicts.

Gap note: inplay_winprob.py (v1/v2/v3 boosters) and live_quantile_bands.py do
NOT currently consume quarter_features columns in their trained feature schemas.
The v1 schema has 8-10 features; v2/v3 add ~11 more but none are from this
parquet.  Injecting novel keys into the feature dict is safe — LightGBM boosters
ignore unknown columns when predict() is called with a DataFrame (unknown columns
are simply absent from the frame built by _feature_frame / _v2_feature_frame).

Usage pattern (caller opts in):
    from src.prediction.quarter_feature_helper import inject_quarter_features
    feats = features_from_snapshot(snap)            # existing inplay builder
    feats = inject_quarter_features(team_id, game_id, feats)
    prob  = predict_home_win_prob(feats, snapshot)

When the parquet row is missing (game not yet cached), the base dict is returned
unchanged so the inplay path degrades gracefully.

The three keys added are chosen as the highest-signal quarter statistics for
in-play win-probability adjustment:
    q1_usg_avg              — team's average Q1 usage rate (star-load signal)
    halftime_pace_shift     — pace change from first half to projected second half
    trailing_team_q4_usg_hhi — Q4 usage concentration on trailing team (desperation proxy)
"""
from __future__ import annotations

from typing import Dict, Optional

from src.data.quarter_features_loader import get_team_quarter_summary


def inject_quarter_features(
    team_id: int,
    game_id: str,
    base_features: Dict,
    *,
    opponent_team_id: Optional[int] = None,
) -> Dict:
    """Merge quarter_features signals into an existing inplay feature dict.

    Parameters
    ----------
    team_id:
        The *home* team ID — used to look up the team-level quarter summary.
    game_id:
        NBA game_id string (e.g. "0022400001").
    base_features:
        The feature dict produced by ``inplay_winprob.features_from_snapshot``.
        Modified in-place and returned.
    opponent_team_id:
        Optional away team ID.  When provided, away-side signals are also
        injected with an ``away_`` prefix.

    Returns
    -------
    dict
        The same ``base_features`` dict with up to 3 (home) + 3 (away) new keys
        appended.  Keys are silently skipped when the parquet row is absent.
    """
    home_summary = get_team_quarter_summary(game_id, team_id)
    if home_summary:
        base_features["q1_usg_avg"] = home_summary["avg_q1_usg"]
        base_features["halftime_pace_shift"] = home_summary["avg_halftime_pace_shift"]
        base_features["trailing_team_q4_usg_hhi"] = home_summary[
            "avg_trailing_team_q4_usg_hhi"
        ]

    if opponent_team_id is not None:
        away_summary = get_team_quarter_summary(game_id, opponent_team_id)
        if away_summary:
            base_features["away_q1_usg_avg"] = away_summary["avg_q1_usg"]
            base_features["away_halftime_pace_shift"] = away_summary[
                "avg_halftime_pace_shift"
            ]
            base_features["away_trailing_team_q4_usg_hhi"] = away_summary[
                "avg_trailing_team_q4_usg_hhi"
            ]

    return base_features


__all__ = ["inject_quarter_features"]
