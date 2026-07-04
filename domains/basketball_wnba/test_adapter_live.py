"""Per-file tests for WNBAAdapter.predict_live (LANE 4: in-game live blend).

Covers: live state parsing into the blend, buzzer exactness (mirrors
domains/basketball_nba/test_nba_live_buzzer.py), tipoff p0-recovery through the
adapter's real Elo baseline_probability, and a static import-scan proving this
adapter touches no placement/trading-config module.

Synthetic data only -- no network, no real corpus dependency.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_adapter_live.py -q
"""
from __future__ import annotations

import ast
import datetime as dt
from pathlib import Path

import pandas as pd
import pytest

from domains.basketball_wnba.adapter import WNBAAdapter, SPORT_ID


def _synthetic_games() -> pd.DataFrame:
    # Enough games + two seasons so walk_forward_elo produces non-degenerate
    # ratings for "Aces" and "Fever" as of the as_of dates used below.
    rows = []
    for i in range(12):
        rows.append({
            "event_id": str(i), "date": pd.Timestamp("2024-05-03") + pd.Timedelta(days=i),
            "season": "2024", "home_team": "Aces", "away_team": "Fever",
            "home_score": 85.0 + i, "away_score": 78.0,
            "home_win": 1.0, "neutral_site": False, "status_name": "STATUS_FINAL",
        })
    return pd.DataFrame(rows)


def _adapter() -> WNBAAdapter:
    return WNBAAdapter(games_df=_synthetic_games())


_AS_OF = dt.datetime(2025, 1, 1)  # strictly after all synthetic games


def test_predict_live_basic_shape():
    a = _adapter()
    out = a.predict_live("Aces", "Fever", _AS_OF, period=2, clock_s=300,
                          home_score=40, away_score=38)
    assert out["sport"] == SPORT_ID
    assert 0.0 <= out["p_home_win"] <= 1.0
    assert out["p_away_win"] == pytest.approx(1.0 - out["p_home_win"], abs=1e-9)
    assert out["score"] == (40.0, 38.0)
    assert "pregame_p_home" in out and 0.0 <= out["pregame_p_home"] <= 1.0


def test_predict_live_tipoff_matches_pregame_p0():
    a = _adapter()
    p0 = a.baseline_probability(
        {"meta": {"home_team": "Aces", "away_team": "Fever"}}, _AS_OF)
    out = a.predict_live("Aces", "Fever", _AS_OF, period=1, clock_s=600,
                          home_score=0, away_score=0)
    assert out["p_home_win"] == pytest.approx(p0, abs=1e-4)
    assert out["pregame_p_home"] == pytest.approx(p0, abs=1e-4)


def test_predict_live_buzzer_decided_win_is_exactly_one():
    a = _adapter()
    out = a.predict_live("Aces", "Fever", _AS_OF, period=4, clock_s=0.0,
                          home_score=90, away_score=80)
    assert out["p_home_win"] == 1.0
    assert out["p_away_win"] == 0.0


def test_predict_live_buzzer_decided_loss_is_exactly_zero():
    a = _adapter()
    out = a.predict_live("Aces", "Fever", _AS_OF, period=4, clock_s=0.0,
                          home_score=80, away_score=90)
    assert out["p_home_win"] == 0.0
    assert out["p_away_win"] == 1.0


def test_predict_live_buzzer_tie_goes_to_blend_not_forced_half():
    # A tie at Q4 0:00 is NOT is_buzzer (goes to OT) -- the value comes from
    # blend_prob, not a hardcoded 0.5, but with score_diff=0 the score term
    # vanishes so it collapses to the (fully-decayed) prior-only term.
    a = _adapter()
    out = a.predict_live("Aces", "Fever", _AS_OF, period=4, clock_s=0.0,
                          home_score=85, away_score=85)
    assert out["p_home_win"] == pytest.approx(0.5, abs=1e-9)


def test_predict_live_neutral_site_flag_recorded_honestly():
    a = _adapter()
    out = a.predict_live("Aces", "Fever", _AS_OF, period=1, clock_s=600,
                          home_score=0, away_score=0, neutral_site=True)
    assert out["neutral_site"] is True
    # Honestly reported as NOT adjusting p0 (no home-tilt term to drop here).
    assert out["neutral_site_adjusted"] is False


def test_predict_live_ot_period_accepted():
    a = _adapter()
    out = a.predict_live("Aces", "Fever", _AS_OF, period=5, clock_s=180,
                          home_score=95, away_score=90)
    assert 0.0 <= out["p_home_win"] <= 1.0
    assert out["period"] == 5


# ---------------------------------------------------------------------------
# static import-scan: no placement/trading-config module reachable
# ---------------------------------------------------------------------------

_BANNED_SUBSTRINGS = (
    "betting_portfolio", "placement", "kalshi_execute", "order_", "stake",
    "bankroll", "trading_config",
)


def _imported_module_names(py_path: Path) -> list[str]:
    tree = ast.parse(py_path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_adapter_and_blend_modules_import_no_placement_path():
    repo_root = Path(__file__).resolve().parents[2]
    for rel in ("domains/basketball_wnba/adapter.py",
                "domains/basketball_wnba/ingame_blend.py"):
        mods = _imported_module_names(repo_root / rel)
        for m in mods:
            low = m.lower()
            for banned in _BANNED_SUBSTRINGS:
                assert banned not in low, f"{rel} imports banned module: {m}"
