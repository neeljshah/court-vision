"""Focused tests for the cross-sport tracking-depth dashboard."""
import json
from types import SimpleNamespace

from scripts.platformkit import depth_dashboard as dashboard


def _ledger_rows():
    rows = []
    for index in range(1, 11):
        rows.append({
            "sport": "tennis", "game_id": f"g{index}", "depth_grade": "B",
            "pct_frames_two_players": float(index),
            "pct_frames_ball": float(index - 1),
            "scored_at": f"2026-08-{index:02d}T00:00:00+00:00",
        })
    return rows


def test_trend_uses_exact_five_game_medians_and_selects_bottleneck():
    report = dashboard.trend(_ledger_rows())["tennis"]

    assert report["current_grade_distribution"] == {"B": 10}
    assert report["last_5_medians"] == {
        "pct_frames_ball": 7.0,
        "pct_frames_two_players": 8.0,
    }
    assert report["previous_5_medians"] == {
        "pct_frames_ball": 2.0,
        "pct_frames_two_players": 3.0,
    }
    assert report["median_change"] == {
        "pct_frames_ball": 5.0,
        "pct_frames_two_players": 5.0,
    }
    assert report["bottleneck"]["metric"] == "pct_frames_two_players"
    assert report["bottleneck"]["threshold"] == 90.0


def test_collect_calls_fixture_probe_flattens_numeric_metrics_and_skips_missing(tmp_path, monkeypatch):
    tracking = tmp_path / "tracking"
    game = tracking / "tennis" / "fixture-game"
    game.mkdir(parents=True)
    (game / "tracking_data.csv").write_text("frame,track_id,cls,x,y\n1,1,player,0,0\n", encoding="utf-8")
    missing = tracking / "missing" / "ignored-game"
    missing.mkdir(parents=True)
    (missing / "tracking_data.csv").write_text("frame,track_id,cls,x,y\n1,1,player,0,0\n", encoding="utf-8")

    fixture = SimpleNamespace(quality_report_csv=lambda path: {
        "pct_frames_two_players": 75.0,
        "court_coverage_sqft_by_player": {1: 12.0, 2: 20.0},
        "depth_grade": "B",
        "ignored_text": "fixture",
    })
    monkeypatch.setitem(dashboard.SPORT_MODULES, "missing", "missing.fixture_probe")
    monkeypatch.setattr(dashboard, "_load_module", lambda sport: fixture if sport == "tennis" else None)
    ledger = tmp_path / "depth_ledger.jsonl"
    monkeypatch.setattr(dashboard, "LEDGER_PATH", ledger)

    rows = dashboard.collect(tmp_path / "reports", tracking)

    assert len(rows) == 1
    assert rows[0]["sport"] == "tennis"
    assert rows[0]["court_coverage_sqft_by_player_min"] == 12.0
    assert json.loads(ledger.read_text(encoding="ascii"))["game_id"] == "fixture-game"


def test_trend_keeps_unknown_sport_without_thresholds():
    report = dashboard.trend([{
        "sport": "cricket", "game_id": "g1", "depth_grade": "C",
        "coverage": 0.0, "scored_at": "2026-08-01T00:00:00+00:00",
    }])["cricket"]

    assert report["current_grade_distribution"] == {"C": 1}
    assert report["bottleneck"] is None
