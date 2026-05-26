"""tests/test_R29_V8_gate1_clv.py — R29_V8 Gate-1 CLV vs Pinnacle.

Validates the gate1_clv_pinnacle script:
  * CLV math correct for known scenarios
  * open-vs-close pairing picks earliest + latest captured_at
  * OUT players filtered (R22_O8 invariant)
  * Kelly invariant respected (R19_L2: never > KELLY_PCT_MAX)
  * Per-stat aggregation correct
  * Empty-data path is graceful
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from scripts.gate1_clv_pinnacle import (  # noqa: E402
    _compute_clv_for_pair,
    _kelly_fraction,
    _pair_open_close_rows,
    aggregate_bets,
    evaluate_date,
    run,
)
from src.prediction.betting_portfolio import KELLY_PCT_MAX  # noqa: E402


# --------------------------------------------------------------------------- #
# CLV math — known cases                                                       #
# --------------------------------------------------------------------------- #

def test_clv_positive_when_close_shorter_than_open():
    """Open at -110, close at -130: positive CLV (we took the better price)."""
    pair = {
        "open_over_price": -110,
        "open_under_price": -110,
        "close_over_price": -130,
        "close_under_price": +110,
    }
    clv = _compute_clv_for_pair(pair, side="over")
    assert clv is not None
    assert clv > 0, f"Expected positive CLV, got {clv}"


def test_clv_zero_when_open_equals_close():
    """No line movement → CLV is exactly 0."""
    pair = {
        "open_over_price": -110,
        "open_under_price": -110,
        "close_over_price": -110,
        "close_under_price": -110,
    }
    clv = _compute_clv_for_pair(pair, side="over")
    assert clv == 0.0


def test_clv_negative_when_close_longer_than_open():
    """Open at -110, close at +100: negative CLV (line moved against us)."""
    pair = {
        "open_over_price": -110,
        "open_under_price": -110,
        "close_over_price": +100,
        "close_under_price": -130,
    }
    clv = _compute_clv_for_pair(pair, side="over")
    assert clv is not None
    assert clv < 0


def test_clv_bad_odds_returns_none():
    """Non-numeric or missing prices → None (graceful)."""
    pair = {
        "open_over_price": "N/A",
        "open_under_price": -110,
        "close_over_price": -110,
        "close_under_price": -110,
    }
    assert _compute_clv_for_pair(pair, side="over") is None


# --------------------------------------------------------------------------- #
# open-vs-close pairing                                                        #
# --------------------------------------------------------------------------- #

def test_pair_picks_earliest_open_latest_close():
    rows = [
        {"captured_at": "2026-05-26T15:00", "game_id": "1", "player_name": "X",
         "stat": "pts", "line": "10.5", "over_price": -120, "under_price": +100},
        {"captured_at": "2026-05-26T12:00", "game_id": "1", "player_name": "X",
         "stat": "pts", "line": "10.5", "over_price": -100, "under_price": -120},
        {"captured_at": "2026-05-26T18:00", "game_id": "1", "player_name": "X",
         "stat": "pts", "line": "10.5", "over_price": -130, "under_price": +110},
    ]
    pairs = _pair_open_close_rows(rows)
    assert len(pairs) == 1
    p = pairs[0]
    assert p["open_captured_at"] == "2026-05-26T12:00"
    assert p["close_captured_at"] == "2026-05-26T18:00"
    assert p["open_over_price"] == -100
    assert p["close_over_price"] == -130


def test_pair_skips_single_capture():
    """Only one captured_at → no pair produced."""
    rows = [
        {"captured_at": "2026-05-26T12:00", "game_id": "1", "player_name": "X",
         "stat": "pts", "line": "10.5", "over_price": -100, "under_price": -120},
    ]
    assert _pair_open_close_rows(rows) == []


def test_pair_groups_by_line_change():
    """Different lines for the same player/stat → separate groups, neither pairs
    if each line only has one capture."""
    rows = [
        {"captured_at": "2026-05-26T12:00", "game_id": "1", "player_name": "X",
         "stat": "pts", "line": "10.5", "over_price": -100, "under_price": -120},
        {"captured_at": "2026-05-26T18:00", "game_id": "1", "player_name": "X",
         "stat": "pts", "line": "11.5", "over_price": -100, "under_price": -120},
    ]
    pairs = _pair_open_close_rows(rows)
    assert pairs == []  # different lines, each only one capture


# --------------------------------------------------------------------------- #
# Kelly invariant (R19_L2)                                                     #
# --------------------------------------------------------------------------- #

def test_kelly_never_exceeds_cap():
    """Even with model_prob ≈ 1.0, quarter-Kelly is clamped to KELLY_PCT_MAX."""
    for prob in (0.55, 0.65, 0.80, 0.95, 0.999):
        for odds in (-150, -110, +100, +150, +300):
            k = _kelly_fraction(prob, odds)
            assert 0.0 <= k <= KELLY_PCT_MAX, (
                f"Kelly {k} out of [0, {KELLY_PCT_MAX}] for prob={prob} odds={odds}"
            )


def test_kelly_zero_when_no_edge():
    """model_prob ≤ implied → no bet (Kelly = 0)."""
    # -110 implies 0.524 → model_prob 0.50 has no edge
    k = _kelly_fraction(0.50, -110)
    assert k == 0.0


# --------------------------------------------------------------------------- #
# Per-stat aggregation                                                         #
# --------------------------------------------------------------------------- #

def test_aggregate_overall_and_per_stat():
    bets = [
        {"date": "2026-05-26", "stat": "pts", "clv_pct": 2.0, "edge_units": 1.0},
        {"date": "2026-05-26", "stat": "pts", "clv_pct": -1.0, "edge_units": 0.5},
        {"date": "2026-05-26", "stat": "reb", "clv_pct": 3.0, "edge_units": 0.3},
        {"date": "2026-05-26", "stat": "reb", "clv_pct": 5.0, "edge_units": 0.2},
    ]
    agg = aggregate_bets(bets)
    assert agg["overall"]["n_bets"] == 4
    assert agg["overall"]["n_distinct_dates"] == 1
    # overall mean: (2 -1 + 3 + 5) / 4 = 2.25
    assert agg["overall"]["mean_clv_pct"] == pytest.approx(2.25, abs=1e-6)
    # 3 of 4 are positive
    assert agg["overall"]["n_positive_clv"] == 3
    assert agg["overall"]["positive_clv_rate"] == 0.75

    assert agg["per_stat"]["pts"]["n_bets"] == 2
    assert agg["per_stat"]["pts"]["mean_clv_pct"] == pytest.approx(0.5, abs=1e-6)
    assert agg["per_stat"]["pts"]["positive_clv_rate"] == 0.5
    assert agg["per_stat"]["reb"]["n_bets"] == 2
    assert agg["per_stat"]["reb"]["mean_clv_pct"] == pytest.approx(4.0, abs=1e-6)
    assert agg["per_stat"]["reb"]["positive_clv_rate"] == 1.0


def test_aggregate_empty_graceful():
    agg = aggregate_bets([])
    assert agg["overall"]["n_bets"] == 0
    assert agg["overall"]["mean_clv_pct"] == 0.0
    assert agg["per_stat"] == {}


# --------------------------------------------------------------------------- #
# Empty-data path                                                              #
# --------------------------------------------------------------------------- #

def test_evaluate_date_missing_file_graceful(tmp_path):
    bets, diag = evaluate_date("2099-01-01", tmp_path / "nope.csv")
    assert bets == []
    assert diag["n_eligible"] == 0
    assert diag["reason_skipped"].get("file_missing") == 1


def test_run_no_files_returns_zero(tmp_path, monkeypatch):
    """run() with no Pin files in the window should not crash."""
    import scripts.gate1_clv_pinnacle as mod

    # Point _LINES_DIR somewhere empty
    monkeypatch.setattr(mod, "_LINES_DIR", tmp_path)
    monkeypatch.setattr(mod, "_RESULTS_PATH", tmp_path / "out.json")
    monkeypatch.setattr(mod, "_CACHE_DIR", tmp_path)
    result = mod.run(days=7, min_stat_coverage=10, write_results=False)
    assert result["n_eligible_bets"] == 0
    assert result["n_pin_files_scanned"] == 0
    assert result["per_stat"] == {}


# --------------------------------------------------------------------------- #
# OUT-player filter (R22_O8)                                                   #
# --------------------------------------------------------------------------- #

def test_out_player_filter_via_synthetic_dirs(tmp_path, monkeypatch):
    """OUT players must be filtered from the bet list."""
    import csv as _csv
    import scripts.gate1_clv_pinnacle as mod

    pd = pytest.importorskip("pandas")

    lines_dir = tmp_path / "lines"
    cache_dir = tmp_path / "cache"
    lines_dir.mkdir()
    cache_dir.mkdir()
    monkeypatch.setattr(mod, "_LINES_DIR", lines_dir)
    monkeypatch.setattr(mod, "_CACHE_DIR", cache_dir)

    # Pin CSV with 2 players, both have opening+closing captures
    pin_path = lines_dir / "2030-01-01_pin.csv"
    with open(pin_path, "w", encoding="utf-8", newline="") as fh:
        w = _csv.writer(fh)
        w.writerow(["captured_at", "book", "game_id", "player_id", "player_name",
                    "stat", "line", "over_price", "under_price", "start_time"])
        for player in ("Healthy Hank", "OUT Oliver"):
            w.writerow(["2030-01-01T12:00", "pin", "g1", "", player,
                        "pts", "10.5", -110, -110, "2030-01-01T19:00Z"])
            w.writerow(["2030-01-01T18:00", "pin", "g1", "", player,
                        "pts", "10.5", -130, +110, "2030-01-01T19:00Z"])

    # Predictions for both players
    preds_df = pd.DataFrame([
        {"player_id": 1, "player_name": "Healthy Hank", "team": "X", "stat": "pts",
         "q10": 5.0, "q50": 12.0, "q90": 18.0, "sigma": 3.0, "computed_at": "x"},
        {"player_id": 2, "player_name": "OUT Oliver", "team": "X", "stat": "pts",
         "q10": 5.0, "q50": 13.0, "q90": 18.0, "sigma": 3.0, "computed_at": "x"},
    ])
    preds_df.to_parquet(cache_dir / "predictions_cache_2030-01-01.parquet")

    # Injury cache marking Oliver OUT
    inj_df = pd.DataFrame([
        {"player_id": 2, "player_name": "OUT Oliver", "team": "X", "status": "OUT",
         "availability_factor": 0.0, "reason": "test", "source": "test",
         "fetched_at": "x", "report_date": "2030-01-01"},
    ])
    inj_df.to_parquet(cache_dir / "nba_injuries_2030-01-01.parquet")

    bets, diag = evaluate_date("2030-01-01", pin_path)
    names = {b["player_name"] for b in bets}
    assert "Healthy Hank" in names
    assert "OUT Oliver" not in names
    assert diag["reason_skipped"].get("player_out") == 1
