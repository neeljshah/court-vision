"""tests/test_defender_matchup.py — Swish-demo defender-matchup residual.

Exercises the standalone module (the live-engine wiring lives separately
in tests/test_live_engine*.py — we test the math here in isolation).

The fixture builds a fake snapshot where Wemby is on offense with
Hartenstein as defender, then asserts:

  1. The (Wemby, Hartenstein) pair triggers the multiplier (≥ 30 partial
     possessions in the real CSV).
  2. The adjusted PTS projection is STRICTLY GREATER than the input
     projection (Wemby shoots over Hartenstein: 90 partial poss → 37
     PTS allowed, well above his series per-poss rate).
  3. The (Wemby, Holmgren) pair pulls PTS DOWN (8 PTS on 52 partial
     poss is below Wemby's series rate).
  4. Missing-defender snapshots no-op cleanly.
  5. Low-sample pairs return the reason ``matchup_skip:low_sample:...``.
"""
from __future__ import annotations

import os
import sys

import pytest

# Project root on sys.path so `src.prediction.*` resolves under pytest.
_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_DIR not in sys.path:
    sys.path.insert(0, _PROJECT_DIR)

from src.prediction.defender_matchup_residual import (    # noqa: E402
    apply_matchup_adjustment,
    load_matchup_table,
    load_series_avg_table,
    _reset_caches_for_test,
)


# Real IDs from data/cache/intel_2026-05-26/wcf_defensive_matchups.csv
WEMBY = 1641705
HARTENSTEIN = 1628392
HOLMGREN = 1631096
SGA = 1628983
VASSELL = 1630170

PROJECT_DIR = _PROJECT_DIR
MATCHUP_CSV = os.path.join(
    PROJECT_DIR, "data", "cache", "intel_2026-05-26",
    "wcf_defensive_matchups.csv",
)
SERIES_CSV = os.path.join(
    PROJECT_DIR, "data", "cache", "intel_2026-05-26",
    "wcf_player_series_avg.csv",
)


@pytest.fixture(autouse=True)
def _clear_module_caches():
    """Ensure each test sees a fresh DataFrame load (cheap — small CSVs)."""
    _reset_caches_for_test()
    yield
    _reset_caches_for_test()


@pytest.fixture
def matchup_df():
    if not os.path.isfile(MATCHUP_CSV):
        pytest.skip("WCF matchup CSV not present on this machine")
    return load_matchup_table(path=MATCHUP_CSV)


@pytest.fixture
def series_df():
    if not os.path.isfile(SERIES_CSV):
        pytest.skip("WCF series-avg CSV not present on this machine")
    return load_series_avg_table(path=SERIES_CSV)


def _wemby_snapshot(defender_id):
    """Minimal snapshot with Wemby on offense + the requested defender."""
    return {
        "game_id": "9999",
        "period": 4,
        "clock": "12:00",
        "home_team": "SAS", "away_team": "OKC",
        "home_score": 70, "away_score": 65,
        "players": [
            {
                "player_id": WEMBY, "name": "Victor Wembanyama", "team": "SAS",
                "min": 28.0, "pts": 22, "reb": 9, "ast": 3, "fg3m": 3,
                "stl": 1, "blk": 2, "tov": 2, "pf": 2,
                "current_defender_id": defender_id,
            },
        ],
    }


def test_wemby_vs_hartenstein_increases_pts(matchup_df, series_df):
    """Hartenstein-on-Wemby: 37 PTS on 90 partial poss → multiplier > 1.0."""
    snap = _wemby_snapshot(HARTENSTEIN)
    base = 30.0    # Wemby series avg pts_pg = 30.25
    adj, reason = apply_matchup_adjustment(
        WEMBY, "pts", base, snapshot=snap,
        matchup_df=matchup_df, series_df=series_df,
    )
    assert reason.startswith("matchup_applied"), reason
    assert adj > base, (
        f"Wemby vs Hartenstein should scale PTS up; got base={base} "
        f"adj={adj} ({reason})"
    )
    # Sanity: multiplier capped at 1.55.
    assert adj <= base * 1.55 + 1e-6


def test_wemby_vs_holmgren_decreases_pts(matchup_df, series_df):
    """Holmgren-on-Wemby: 8 PTS on 52 partial poss → multiplier < 1.0."""
    snap = _wemby_snapshot(HOLMGREN)
    base = 30.0
    adj, reason = apply_matchup_adjustment(
        WEMBY, "pts", base, snapshot=snap,
        matchup_df=matchup_df, series_df=series_df,
    )
    assert reason.startswith("matchup_applied"), reason
    assert adj < base, (
        f"Wemby vs Holmgren should scale PTS down; got base={base} "
        f"adj={adj} ({reason})"
    )
    assert adj >= base * 0.55 - 1e-6


def test_hartenstein_vs_holmgren_separation(matchup_df, series_df):
    """The Hartenstein adjusted projection should EXCEED the Holmgren one."""
    base = 30.0
    snap_h = _wemby_snapshot(HARTENSTEIN)
    adj_h, _ = apply_matchup_adjustment(
        WEMBY, "pts", base, snapshot=snap_h,
        matchup_df=matchup_df, series_df=series_df,
    )
    snap_c = _wemby_snapshot(HOLMGREN)
    adj_c, _ = apply_matchup_adjustment(
        WEMBY, "pts", base, snapshot=snap_c,
        matchup_df=matchup_df, series_df=series_df,
    )
    assert adj_h > adj_c, (
        f"Hartenstein-defended Wemby ({adj_h}) should project HIGHER than "
        f"Holmgren-defended Wemby ({adj_c})"
    )


def test_no_defender_in_snapshot_noop(matchup_df, series_df):
    """When the snapshot omits defender info, projection passes through."""
    snap = {
        "game_id": "9999", "period": 4, "clock": "12:00",
        "home_team": "SAS", "away_team": "OKC",
        "home_score": 70, "away_score": 65,
        "players": [
            {"player_id": WEMBY, "name": "Wembanyama", "team": "SAS",
             "min": 28.0, "pts": 22, "pf": 2},
        ],
    }
    base = 30.0
    adj, reason = apply_matchup_adjustment(
        WEMBY, "pts", base, snapshot=snap,
        matchup_df=matchup_df, series_df=series_df,
    )
    assert adj == base
    assert reason == "matchup_skip:defender_not_in_snapshot"


def test_explicit_defender_id_kwarg(matchup_df, series_df):
    """Caller can pass defender_id explicitly, bypassing the snapshot path."""
    base = 30.0
    adj, reason = apply_matchup_adjustment(
        WEMBY, "pts", base, snapshot=None, defender_id=HARTENSTEIN,
        matchup_df=matchup_df, series_df=series_df,
    )
    assert reason.startswith("matchup_applied"), reason
    assert adj > base


def test_missing_pair_skip(matchup_df, series_df):
    """A pair that doesn't exist in the tape returns pair_not_in_table."""
    base = 30.0
    adj, reason = apply_matchup_adjustment(
        WEMBY, "pts", base, snapshot=None, defender_id=99999999,
        matchup_df=matchup_df, series_df=series_df,
    )
    assert adj == base
    assert "pair_not_in_table" in reason


def test_sga_vs_vassell_decreases_pts(matchup_df, series_df):
    """SGA vs Vassell: 12 PTS on 89.3 partial poss vs series avg 24.75 pg."""
    base = 25.0
    adj, reason = apply_matchup_adjustment(
        SGA, "pts", base, snapshot=None, defender_id=VASSELL,
        matchup_df=matchup_df, series_df=series_df,
    )
    assert reason.startswith("matchup_applied"), reason
    assert adj < base, (
        f"SGA vs Vassell should scale PTS down; got {adj} from {base}"
    )


def test_reb_stat_unsupported(matchup_df, series_df):
    """Rebounds aren't in the matchup tape — skip gracefully."""
    base = 13.0
    adj, reason = apply_matchup_adjustment(
        WEMBY, "reb", base, snapshot=None, defender_id=HARTENSTEIN,
        matchup_df=matchup_df, series_df=series_df,
    )
    assert adj == base
    assert reason.startswith("matchup_skip:stat_not_supported")
