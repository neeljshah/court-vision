"""Tests for the tracking-quality improvement brain.

Run: python -m pytest scripts/platformkit/test_tracking_brain.py -q
"""
import json

from scripts.platformkit.tracking_brain import next_actions, scorecard


def _write_report(root, sport, name, **values):
    folder = root / sport
    folder.mkdir(parents=True, exist_ok=True)
    report = {
        "sport": sport, "coverage_pct": 0.95, "ball_valid_pct": 0.95,
        "jump_p95": 1.0, "oob_pct": 0.01, "passed": True,
    }
    report.update(values)
    (folder / name).write_text(json.dumps(report), encoding="utf-8")


def test_scorecard_selects_closest_metric_and_actions_rank(tmp_path):
    _write_report(tmp_path, "basketball", "one.json", coverage_pct=0.91,
                  ball_valid_pct=0.20, passed=False)
    _write_report(tmp_path, "basketball", "two.json", coverage_pct=0.92,
                  ball_valid_pct=0.25, passed=False)
    _write_report(tmp_path, "tennis", "one.json", jump_p95=9.0, passed=False)
    (tmp_path / "ledger.jsonl").write_text(
        json.dumps({"ts": "now", "game_id": "t1", "sport": "tennis",
                    "status": "skipped", "report": {}}) + "\n",
        encoding="utf-8",
    )

    card = scorecard("basketball", tmp_path)
    assert card["worst_metric"] == "ball_valid"
    assert card["games_scored"] == 2
    assert card["pass_rate"] == 0.0

    actions = next_actions(tmp_path)
    assert all(action["priority"] == 1 for action in actions[:2])
    assert any(action["suggested_action"] == "ball detector upgrade (TrackNet-class)"
               for action in actions)
    assert any(action["reason"] == "not_implemented tracker" and action["sport"] == "tennis"
               for action in actions)
