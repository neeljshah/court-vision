"""test_L19_clv.py — Tests for L19_clv_calculator.py

Ten tests using frozen fixtures only — no live data, no NBA API.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

# -- ensure project root on path -------------------------------------------
_TEST_DIR = Path(__file__).resolve().parent
_LOOP_DIR = _TEST_DIR.parent
_PROJECT_DIR = _LOOP_DIR.parents[1]
sys.path.insert(0, str(_PROJECT_DIR))
sys.path.insert(0, str(_LOOP_DIR))

import L19_clv_calculator as L19  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_SIGMA_PTS = L19.BASE_SIGMA["pts"] * L19.SIGMA_MULT["pts"]   # 6.0 * 1.07 = 6.42
_PDF0 = L19._PDF0


def _make_bet(
    bet_id="b1",
    book="prizepicks",
    market="player_prop_pts",
    side="OVER",
    stat="pts",
    line=20.5,
    placed_at="2026-05-25T18:00:00",
    model_p=0.55,
    status="WON",
):
    return {
        "bet_id": bet_id,
        "book": book,
        "market": market,
        "side": side,
        "stat": stat,
        "line": line,
        "placed_at_iso": placed_at,
        "model_p_side": model_p,
        "status": status,
        "player": "LeBron James",
        "stake": 10.0,
        "pnl": 9.09,
    }


def _make_bets_df(bets_list):
    return pd.DataFrame(bets_list)


def _make_snaps_df(rows):
    """rows: list of (snapshot_ts str, player, stat, line)"""
    records = []
    for ts_str, player, stat, line in rows:
        records.append({
            "snapshot_ts": datetime.fromisoformat(ts_str),
            "player_norm": L19._norm_player(player),
            "stat": stat,
            "line": float(line),
            "book": "prizepicks",
        })
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Test 1: OVER 20.5 → 19.5 gives clv_units = +1.0
# ---------------------------------------------------------------------------
def test_compute_clv_over_line_drops():
    """OVER: line dropped from 20.5 → 19.5. CLV = +1.0 (good for bettor)."""
    bet = _make_bet(side="OVER", stat="pts")
    point = L19.compute_clv(bet, line_at_bet=20.5, line_at_close=19.5)
    assert point.clv_units == pytest.approx(1.0, abs=1e-6)
    assert point.side == "OVER"
    assert point.line_at_bet == 20.5
    assert point.line_at_close == 19.5


# ---------------------------------------------------------------------------
# Test 2: UNDER 20.5 → 19.5 gives clv_units = -1.0
# ---------------------------------------------------------------------------
def test_compute_clv_under_line_drops():
    """UNDER: line dropped 20.5 → 19.5. CLV = -1.0 (bad for UNDER bettor)."""
    bet = _make_bet(side="UNDER", stat="pts")
    point = L19.compute_clv(bet, line_at_bet=20.5, line_at_close=19.5)
    assert point.clv_units == pytest.approx(-1.0, abs=1e-6)


# ---------------------------------------------------------------------------
# Test 3: OVER 20.5 → 21.5 gives clv_units = -1.0
# ---------------------------------------------------------------------------
def test_compute_clv_over_line_rises():
    """OVER: line rose 20.5 → 21.5. CLV = -1.0 (line moved against bettor)."""
    bet = _make_bet(side="OVER", stat="pts")
    point = L19.compute_clv(bet, line_at_bet=20.5, line_at_close=21.5)
    assert point.clv_units == pytest.approx(-1.0, abs=1e-6)


# ---------------------------------------------------------------------------
# Test 4: clv_prob_pts for OVER pts 20.5→19.5 ≈ +6.2pp
# ---------------------------------------------------------------------------
def test_clv_prob_pts_over_pts_1unit():
    """OVER pts, clv_units=+1.0, sigma_pts=6.42 → clv_prob_pts ≈ +6.21 pp."""
    bet = _make_bet(side="OVER", stat="pts")
    point = L19.compute_clv(bet, line_at_bet=20.5, line_at_close=19.5)
    expected = (1.0 / _SIGMA_PTS) * 100.0 * _PDF0
    assert point.clv_prob_pts == pytest.approx(expected, rel=1e-4)
    # Must be roughly +6.2 pp (sanity range check)
    assert 5.5 < point.clv_prob_pts < 7.0


# ---------------------------------------------------------------------------
# Test 5: join_bets_to_closes with frozen 2-bet / 4-snapshot DataFrame
# ---------------------------------------------------------------------------
def test_join_bets_to_closes_correct_lines():
    """Frozen 2-bet / 4-snapshot join: correct line_at_bet and line_at_close."""
    bets = _make_bets_df([
        _make_bet("b1", side="OVER", stat="pts", line=20.5,
                  placed_at="2026-05-25T18:00:00", model_p=0.55),
        _make_bet("b2", side="UNDER", stat="reb", line=8.5,
                  placed_at="2026-05-25T18:00:00", model_p=0.48),
    ])
    snaps = _make_snaps_df([
        # pts snapshots for LeBron James
        ("2026-05-25T17:00:00", "LeBron James", "pts", 21.5),  # before bet
        ("2026-05-25T17:45:00", "LeBron James", "pts", 20.5),  # at bet time — latest before
        ("2026-05-25T19:00:00", "LeBron James", "pts", 19.5),  # after bet — becomes close
        # reb snapshot for LeBron James
        ("2026-05-25T17:45:00", "LeBron James", "reb", 8.5),
    ])
    result = L19.join_bets_to_closes(bets, snaps)
    assert len(result) == 2

    b1 = result[result["bet_id"] == "b1"].iloc[0]
    assert b1["line_at_bet_snap"] == pytest.approx(20.5, abs=1e-3)
    assert b1["line_at_close_snap"] == pytest.approx(19.5, abs=1e-3)
    # OVER line dropped → positive CLV
    assert b1["clv_units"] == pytest.approx(1.0, abs=1e-3)

    b2 = result[result["bet_id"] == "b2"].iloc[0]
    assert b2["line_at_bet_snap"] is not None
    assert b2["skipped_reason"] in ("", None)


# ---------------------------------------------------------------------------
# Test 6: alt-line collapse picks median-nearest
# ---------------------------------------------------------------------------
def test_alt_line_collapse_picks_median():
    """Alt-line collapse: per (player_norm, stat, snapshot_ts) keeps line nearest median."""
    # Three alt lines at the same snapshot timestamp; median = 20.5
    rows = [
        {"snapshot_ts": datetime(2026, 5, 25, 17, 0), "player_norm": "lebron james",
         "stat": "pts", "line": 19.5, "book": "prizepicks"},
        {"snapshot_ts": datetime(2026, 5, 25, 17, 0), "player_norm": "lebron james",
         "stat": "pts", "line": 20.5, "book": "prizepicks"},
        {"snapshot_ts": datetime(2026, 5, 25, 17, 0), "player_norm": "lebron james",
         "stat": "pts", "line": 22.0, "book": "prizepicks"},
    ]
    raw = pd.DataFrame(rows)

    # Replicate the collapse logic from load_snapshots
    grp = raw.groupby(["player_norm", "stat", "snapshot_ts"])["line"]
    medians = grp.transform("median")
    raw["_dist"] = (raw["line"] - medians).abs()
    collapsed = (
        raw.sort_values("_dist")
        .drop_duplicates(subset=["player_norm", "stat", "snapshot_ts"])
        .drop(columns=["_dist"])
        .reset_index(drop=True)
    )
    assert len(collapsed) == 1
    assert collapsed.iloc[0]["line"] == pytest.approx(20.5, abs=1e-3)


# ---------------------------------------------------------------------------
# Test 7: nightly_clv_report writes JSON with all required keys
# ---------------------------------------------------------------------------
def test_nightly_clv_report_writes_json(tmp_path):
    """nightly_clv_report writes valid JSON with all required top-level keys."""
    bets = _make_bets_df([
        _make_bet("b1", side="OVER", stat="pts", line=20.5,
                  placed_at="2026-05-25T18:00:00"),
    ])
    snaps = _make_snaps_df([
        ("2026-05-25T17:45:00", "LeBron James", "pts", 21.0),
        ("2026-05-25T19:00:00", "LeBron James", "pts", 19.5),
    ])

    with (
        patch.object(L19, "_load_bets", return_value=bets),
        patch.object(L19, "load_snapshots", return_value=snaps),
        patch.object(L19, "_LEDGER_DIR", tmp_path),
        patch.object(L19, "rolling_clv_trend", return_value={"daily_trend": [], "overall_mean_clv_pp": 0.5}),
        patch.object(L19, "alert_clv_drift", return_value=[]),
    ):
        report = L19.nightly_clv_report(date="2026-05-25")

    required_keys = {
        "date", "n_bets_with_clv", "n_skipped_no_close", "n_skipped_live",
        "mean_clv_units", "mean_clv_prob_pts", "pct_positive_clv",
        "per_stat_clv", "per_book_clv", "top5_best", "top5_worst",
        "rolling14d", "drift_warning",
    }
    assert required_keys.issubset(set(report.keys())), (
        f"Missing keys: {required_keys - set(report.keys())}"
    )

    # Verify JSON on disk
    json_path = tmp_path / "clv_report_2026-05-25.json"
    assert json_path.exists()
    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert loaded["date"] == "2026-05-25"
    assert required_keys.issubset(set(loaded.keys()))


# ---------------------------------------------------------------------------
# Test 8: alert_clv_drift returns [] when mean > 0; list when < threshold
# ---------------------------------------------------------------------------
def test_alert_clv_drift_positive_no_alert():
    """No alert when 14-day mean CLV is positive."""
    positive_trend = {"days": 14, "overall_mean_clv_pp": 1.5, "daily_trend": []}
    with patch.object(L19, "rolling_clv_trend", return_value=positive_trend):
        alerts = L19.alert_clv_drift(window_days=14, threshold_pp=-2.0)
    assert alerts == []


def test_alert_clv_drift_below_threshold():
    """Alert returned when 14-day mean CLV < -2.0 pp."""
    bad_trend = {"days": 14, "overall_mean_clv_pp": -3.0, "daily_trend": []}
    with patch.object(L19, "rolling_clv_trend", return_value=bad_trend):
        alerts = L19.alert_clv_drift(window_days=14, threshold_pp=-2.0)
    assert len(alerts) == 1
    assert alerts[0]["type"] == "CLV_DRIFT"
    assert alerts[0]["mean_clv_pp"] == pytest.approx(-3.0, abs=1e-6)
    assert "CLV drift detected" in alerts[0]["message"]


# ---------------------------------------------------------------------------
# Test 9: bet placed after tipoff (market=live) counted in n_skipped_live
# ---------------------------------------------------------------------------
def test_live_bet_excluded_from_clv(tmp_path):
    """Bets with market='live' are excluded from CLV and counted in n_skipped_live."""
    bets = _make_bets_df([
        _make_bet("b_live", market="live", side="OVER", stat="pts",
                  line=20.5, placed_at="2026-05-25T21:00:00"),
        _make_bet("b_pre", market="player_prop_pts", side="OVER", stat="pts",
                  line=20.5, placed_at="2026-05-25T18:00:00"),
    ])
    snaps = _make_snaps_df([
        ("2026-05-25T17:45:00", "LeBron James", "pts", 21.0),
        ("2026-05-25T19:00:00", "LeBron James", "pts", 19.5),
    ])

    with (
        patch.object(L19, "_load_bets", return_value=bets),
        patch.object(L19, "load_snapshots", return_value=snaps),
        patch.object(L19, "_LEDGER_DIR", tmp_path),
        patch.object(L19, "rolling_clv_trend", return_value={"daily_trend": [], "overall_mean_clv_pp": 0.0}),
        patch.object(L19, "alert_clv_drift", return_value=[]),
    ):
        report = L19.nightly_clv_report(date="2026-05-25")

    assert report["n_skipped_live"] >= 1, "live bet should increment n_skipped_live"


# ---------------------------------------------------------------------------
# Test 10: Push/void bet still produces a CLVPoint
# ---------------------------------------------------------------------------
def test_push_bet_produces_clv_point():
    """Push bets should still compute CLV — outcome doesn't affect CLV math."""
    bet = _make_bet(side="OVER", stat="pts", status="PUSH")
    point = L19.compute_clv(bet, line_at_bet=20.5, line_at_close=20.0)
    assert isinstance(point, L19.CLVPoint)
    assert point.clv_units == pytest.approx(0.5, abs=1e-6)
    assert isinstance(point.clv_prob_pts, float)
    assert point.bet_id == "b1"
