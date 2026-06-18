"""Leak-free expected-minutes model for soccer player props.

Estimates how many minutes a player is likely to play in an upcoming match from
their OWN prior matches (date STRICTLY BEFORE as_of_date). We do NOT invent a
lineup: when a player has no prior history we return status "unknown" and the
caller must supply minutes or treat the player as not playing.

Public functions NEVER raise.

Run the per-file test (full pytest freezes the box):
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/test_player_minutes.py -q
"""
from __future__ import annotations

from typing import Dict

import pandas as pd

from domains.soccer.player_rates import _prior_rows

# A nominal "full match" worth of minutes for a starter (90' minus typical
# stoppage subs); used as the start branch of the minutes expectation.
_START_MINUTES = 85.0
# A player who has ALWAYS started gets the optimistic full-starter expectation.
_PURE_START_MINUTES = 88.0
_EPS = 1e-9


def expected_minutes(df: pd.DataFrame, player_id, as_of_date) -> Dict[str, object]:
    """Expected minutes + start probability for one player.

    Returns {"e_minutes": float, "start_prob": float, "status": "ok"|"unknown"}.

    Method (leak-free, uses only rows before as_of_date):
      start_prob   = P(starter) over prior matches.
      avg_sub_min  = mean observed minutes in matches the player did NOT start.
      e_minutes    = start_prob * START_MINUTES + (1 - start_prob) * avg_sub_min.
    Special cases: always started -> PURE_START_MINUTES; pure sub -> avg_sub_min.
    No prior history -> status "unknown" (never fabricate a lineup).
    """
    unknown = {"e_minutes": None, "start_prob": None, "status": "unknown"}

    prior = _prior_rows(df, as_of_date)
    if prior is None or len(prior) == 0:
        return dict(unknown)

    pid = str(player_id)
    if "player_id" in prior.columns:
        own = prior.loc[prior["player_id"].astype(str) == pid]
    else:
        own = prior.iloc[0:0]
    if len(own) == 0:
        return dict(unknown)

    if "starter" not in own.columns:
        return dict(unknown)

    starter = own["starter"].fillna(False).astype(bool)
    n = int(len(starter))
    start_prob = float(starter.sum()) / n if n > 0 else 0.0

    minutes = pd.to_numeric(own.get("minutes"), errors="coerce").fillna(0.0)
    sub_minutes = minutes.loc[~starter]

    if start_prob >= 1.0 - _EPS:
        # Always started.
        return {
            "e_minutes": _PURE_START_MINUTES,
            "start_prob": 1.0,
            "status": "ok",
        }

    if len(sub_minutes) > 0:
        avg_sub = float(sub_minutes.mean())
    else:
        avg_sub = 0.0

    if start_prob <= _EPS:
        # Pure sub -> their observed average sub minutes.
        return {
            "e_minutes": float(avg_sub),
            "start_prob": 0.0,
            "status": "ok",
        }

    e_minutes = start_prob * _START_MINUTES + (1.0 - start_prob) * avg_sub
    return {
        "e_minutes": float(e_minutes),
        "start_prob": float(start_prob),
        "status": "ok",
    }
