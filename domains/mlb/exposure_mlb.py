"""Leak-free expected-exposure models for MLB player props.

Mirrors domains/soccer/player_minutes.py but MLB exposure differs by role:
  - BATTERS: exposure = expected plate appearances (PA) in the game. From the
    mean of the player's recent PA, or by lineup spot when there is no history.
  - PITCHERS: exposure = expected batters faced (BF). Starter mean BF from recent
    starts (~24); relievers face far fewer.

Every estimate uses ONLY rows whose ``date`` is STRICTLY BEFORE ``as_of`` (leak
guard). Public functions NEVER raise -- they degrade to {"status": "unknown"} or a
sensible default with status "default". No $-edge claims.

Run the per-file test (full pytest freezes the box):
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/test_exposure_mlb.py -q
"""
from __future__ import annotations

from typing import Dict, Optional

import pandas as pd

from domains.mlb.player_rates_mlb import _own_rows, _pa_total, _prior_rows

_EPS = 1e-9
# Recent window (games) for the exposure mean -- recency beats volume.
_RECENT_GAMES = 15
# Lineup-spot PA priors (typical PA per game by batting-order slot).
_LINEUP_PA = {1: 4.6, 2: 4.5, 3: 4.4, 4: 4.2, 5: 4.1, 6: 4.0, 7: 3.9, 8: 3.8, 9: 3.7}
_DEFAULT_PA = 4.0
# Pitcher BF defaults.
_DEFAULT_STARTER_BF = 24.0
_DEFAULT_BF = 24.0


def _recent(own: pd.DataFrame, n: int) -> pd.DataFrame:
    if "date" not in own.columns or len(own) == 0:
        return own
    ordered = own.assign(_d=pd.to_datetime(own["date"], errors="coerce"))
    ordered = ordered.sort_values("_d").tail(n)
    return ordered.drop(columns=["_d"])


def _lineup_default(batting_order) -> float:
    try:
        slot = int(batting_order)
    except (TypeError, ValueError):
        return _DEFAULT_PA
    return _LINEUP_PA.get(slot, _DEFAULT_PA)


def expected_pa(
    df: pd.DataFrame, player_id, as_of, *, batting_order=None
) -> Dict[str, object]:
    """Expected plate appearances for one batter in the upcoming game.

    Returns {"e_pa": float, "status": "ok"|"default"|"unknown"}.
    Method (leak-free): mean PA over the player's recent games before as_of. With
    no history, falls back to the lineup-spot prior (status "default") when a
    ``batting_order`` is given, else the global default. status "unknown" only when
    inputs are unusable. Never raises.
    """
    prior = _prior_rows(df, as_of)
    if prior is None:
        if batting_order is not None:
            return {"e_pa": float(_lineup_default(batting_order)), "status": "default"}
        return {"e_pa": _DEFAULT_PA, "status": "unknown"}

    own = _recent(_own_rows(prior, player_id), _RECENT_GAMES)
    n_games = int(len(own))
    if n_games > 0:
        e_pa = _pa_total(own) / n_games
        if e_pa > _EPS:
            return {"e_pa": float(e_pa), "status": "ok"}

    if batting_order is not None:
        return {"e_pa": float(_lineup_default(batting_order)), "status": "default"}
    return {"e_pa": _DEFAULT_PA, "status": "default"}


def expected_bf(df: pd.DataFrame, player_id, as_of) -> Dict[str, object]:
    """Expected batters faced for one pitcher in the upcoming start.

    Returns {"e_bf": float, "status": "ok"|"default"|"unknown"}.
    Method (leak-free): mean BF over the pitcher's recent appearances before as_of
    (this naturally separates starters ~24 from relievers via their own history).
    No history -> starter default (status "default"). Never raises.
    """
    prior = _prior_rows(df, as_of)
    if prior is None:
        return {"e_bf": _DEFAULT_STARTER_BF, "status": "unknown"}

    own = _recent(_own_rows(prior, player_id), _RECENT_GAMES)
    n = int(len(own))
    if n > 0 and "battersFaced" in own.columns:
        bf = pd.to_numeric(own["battersFaced"], errors="coerce").fillna(0.0)
        e_bf = float(bf.mean())
        if e_bf > _EPS:
            return {"e_bf": e_bf, "status": "ok"}

    return {"e_bf": _DEFAULT_BF, "status": "default"}
