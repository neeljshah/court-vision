"""tests.soccer.test_ingest_statsbomb_events -- OFFLINE leak-free checks for the
StatsBomb event-level as-of layer. No network: builds tiny SYNTHETIC event streams and
exercises (1) as-of in-game minute-folding (cumulative real xG uses only minute<=t,
never the final total), (2) the strictly-prior pregame EW priors (debut=NaN,
snapshot-before-update, no future leak)."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from domains.soccer.ingest_statsbomb_events import (
    _ingame_snapshots, _team_event_stats, build_pregame_priors,
)


def _shot(team: str, minute: int, xg: float, goal: bool = False) -> dict:
    return {"type": {"name": "Shot"}, "team": {"name": team}, "minute": minute,
            "second": 0, "shot": {"statsbomb_xg": xg,
                                  "outcome": {"name": "Goal" if goal else "Saved"}}}


def _pass(team: str, minute: int, complete: bool) -> dict:
    return {"type": {"name": "Pass"}, "team": {"name": team}, "minute": minute,
            "pass": ({} if complete else {"outcome": {"name": "Incomplete"}})}


def _press(team: str, minute: int) -> dict:
    return {"type": {"name": "Pressure"}, "team": {"name": team}, "minute": minute}


def _events() -> list:
    return [
        _shot("Home", 10, 0.2), _shot("Away", 20, 0.1, goal=True),
        _press("Home", 25), _pass("Home", 26, True), _pass("Home", 27, False),
        _shot("Home", 50, 0.5, goal=True), _press("Away", 55),
        _shot("Away", 80, 0.3),
    ]


def test_ingame_asof_uses_only_past_minutes() -> None:
    """At minute 30, only the two early shots count -- NOT the later 50'/80' shots."""
    rows = _ingame_snapshots(1, "Home", "Away", _events(), step=30)
    by_min = {r["minute"]: r for r in rows}
    r30 = by_min[30]
    # home xg = 0.2 only; away xg = 0.1 only (folded by minute, not final totals)
    assert r30["home_xg_asof"] == pytest.approx(0.2)
    assert r30["away_xg_asof"] == pytest.approx(0.1)
    assert r30["xg_diff_asof"] == pytest.approx(0.1)
    assert r30["goal_diff_asof"] == -1  # only Away's 20' goal so far


def test_ingame_monotone_accumulation() -> None:
    """Cumulative xG never decreases as the snapshot minute advances (as-of)."""
    rows = _ingame_snapshots(1, "Home", "Away", _events(), step=30)
    hx = [r["home_xg_asof"] for r in sorted(rows, key=lambda x: x["minute"])]
    assert all(hx[i] <= hx[i + 1] + 1e-12 for i in range(len(hx) - 1))
    last = max(rows, key=lambda r: r["minute"])
    assert last["home_xg_asof"] == pytest.approx(0.7)  # 0.2 + 0.5 by 90'


def test_ingame_no_future_leak() -> None:
    """Mutating a LATE shot must not change an EARLIER snapshot row (leak-free)."""
    ev = _events()
    base = {r["minute"]: r["xg_diff_asof"]
            for r in _ingame_snapshots(1, "Home", "Away", ev, step=30)}
    ev2 = _events(); ev2[-1]["shot"]["statsbomb_xg"] = 9.9  # mutate the 80' shot
    after = {r["minute"]: r["xg_diff_asof"]
             for r in _ingame_snapshots(1, "Home", "Away", ev2, step=30)}
    assert base[30] == pytest.approx(after[30])
    assert base[60] == pytest.approx(after[60])


def test_team_event_stats_pass_pct() -> None:
    st = _team_event_stats(_events())
    assert st["Home"]["shots"] == 2
    assert st["Home"]["xg"] == pytest.approx(0.7)
    assert st["Home"]["pass_n"] == 2 and st["Home"]["pass_ok"] == 1


def _spine() -> pd.DataFrame:
    """Three chronological matches; Alpha plays all three."""
    return pd.DataFrame([
        {"match_id": "1", "date": "2015-08-01", "home_team": "Alpha",
         "away_team": "Beta", "home_xg_for": 2.0, "home_xg_against": 0.5,
         "away_xg_for": 0.5, "away_xg_against": 2.0, "home_shots": 12, "away_shots": 4,
         "home_press": 50, "away_press": 30, "home_pass_pct": 0.8, "away_pass_pct": 0.6},
        {"match_id": "2", "date": "2015-08-08", "home_team": "Gamma",
         "away_team": "Alpha", "home_xg_for": 1.0, "home_xg_against": 1.5,
         "away_xg_for": 1.5, "away_xg_against": 1.0, "home_shots": 8, "away_shots": 10,
         "home_press": 40, "away_press": 45, "home_pass_pct": 0.7, "away_pass_pct": 0.75},
        {"match_id": "3", "date": "2015-08-15", "home_team": "Alpha",
         "away_team": "Gamma", "home_xg_for": 1.2, "home_xg_against": 0.9,
         "away_xg_for": 0.9, "away_xg_against": 1.2, "home_shots": 9, "away_shots": 7,
         "home_press": 48, "away_press": 42, "home_pass_pct": 0.82, "away_pass_pct": 0.71},
    ])


def test_pregame_debut_is_nan() -> None:
    """First-ever appearance -> prior is NaN (we REFUSE to 0-fill)."""
    pri = build_pregame_priors(_spine()).set_index("match_id")
    assert math.isnan(pri.loc["1", "home_prior_xg_for"])  # Alpha debut
    assert math.isnan(pri.loc["1", "away_prior_xg_for"])  # Beta debut


def test_pregame_strictly_prior_mean() -> None:
    """Alpha's match-3 prior xg_for = mean of its two PRIOR appearances (2.0, 1.5)."""
    pri = build_pregame_priors(_spine()).set_index("match_id")
    assert pri.loc["3", "home_prior_xg_for"] == pytest.approx((2.0 + 1.5) / 2)


def test_pregame_no_future_leak() -> None:
    """Mutating match-3 must not change match-1/2 priors."""
    base = build_pregame_priors(_spine()).set_index("match_id")
    sp = _spine(); sp.loc[2, "home_xg_for"] = 99.0
    after = build_pregame_priors(sp).set_index("match_id")
    for mid in ("1", "2"):
        for c in ("home_prior_xg_for", "away_prior_xg_for"):
            a, b = base.loc[mid, c], after.loc[mid, c]
            assert (math.isnan(a) and math.isnan(b)) or a == pytest.approx(b)
