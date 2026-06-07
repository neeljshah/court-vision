"""tests/test_alert_audit_pages.py — Tests for alert_log and prediction_audit pages.

Covers:
1. load_alerts — no log file → empty list
2. load_alerts — synthetic vault/alerts.log → correct parsed entries
3. list_prediction_files — no directory → empty list
4. load_predictions — list-format JSON → returns list of dicts
"""
from __future__ import annotations

import json
import os

import pytest

# The dashboard pages import streamlit (a dashboard-only optional dependency). When
# it is not installed, skip this whole module rather than aborting collection for the
# ENTIRE test suite (pytest stops on a collection-time ImportError by default). No-op
# when streamlit is present; clean skip when it is not.
pytest.importorskip("streamlit")

from apps.dashboards.pages.alert_log import load_alerts  # noqa: E402
from apps.dashboards.pages.prediction_audit import list_prediction_files, load_predictions  # noqa: E402


# ── load_alerts ───────────────────────────────────────────────────────────────


class TestLoadAlerts:
    def test_load_alerts_empty(self, tmp_path):
        """No log file and no alerts dir → empty list."""
        missing_log = str(tmp_path / "alerts.log")
        missing_dir = str(tmp_path / "alerts")
        result = load_alerts(alerts_log=missing_log, alerts_dir=missing_dir)
        assert result == []

    def test_load_alerts_parses_lines(self, tmp_path):
        """Synthetic alerts.log with two entries → list with correct timestamp/message."""
        log_file = tmp_path / "alerts.log"
        log_file.write_text(
            "2026-05-21T16:00:00Z ALERT scraper timeout\n"
            "2026-05-20T09:30:00Z WARN low confidence prediction\n",
            encoding="utf-8",
        )
        missing_dir = str(tmp_path / "alerts")
        result = load_alerts(alerts_log=str(log_file), alerts_dir=missing_dir)
        # Most recent first (reversed), so originally last line comes first
        assert len(result) == 2
        # After reversal: index 0 is the last line written
        assert result[0]["timestamp"] == "2026-05-20T09:30:00Z"
        assert "low confidence prediction" in result[0]["message"]
        assert result[1]["timestamp"] == "2026-05-21T16:00:00Z"
        assert "scraper timeout" in result[1]["message"]


# ── list_prediction_files ─────────────────────────────────────────────────────


class TestListPredictionFiles:
    def test_list_prediction_files_empty(self, tmp_path):
        """Directory does not exist → empty list."""
        missing_dir = str(tmp_path / "daily_predictions")
        result = list_prediction_files(predictions_dir=missing_dir)
        assert result == []

    def test_list_prediction_files_returns_jsons(self, tmp_path):
        """Directory with JSON files → returns sorted list of absolute paths."""
        pred_dir = tmp_path / "daily_predictions"
        pred_dir.mkdir()
        (pred_dir / "2026-05-20.json").write_text("[]", encoding="utf-8")
        (pred_dir / "2026-05-21.json").write_text("[]", encoding="utf-8")
        result = list_prediction_files(predictions_dir=str(pred_dir))
        assert len(result) == 2
        # Most recent first
        assert os.path.basename(result[0]) == "2026-05-21.json"
        assert os.path.basename(result[1]) == "2026-05-20.json"


# ── load_predictions ──────────────────────────────────────────────────────────


class TestLoadPredictions:
    def test_load_predictions_list_format(self, tmp_path):
        """JSON file containing a list of dicts → returns that list."""
        pred_file = tmp_path / "preds.json"
        payload = [
            {"game_id": "0022501001", "xgb_pred": 0.62, "lgb_pred": 0.58},
            {"game_id": "0022501002", "xgb_pred": 0.44, "lgb_pred": 0.47},
        ]
        pred_file.write_text(json.dumps(payload), encoding="utf-8")
        result = load_predictions(str(pred_file))
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["game_id"] == "0022501001"
        assert result[1]["xgb_pred"] == pytest.approx(0.44)

    def test_load_predictions_dict_format(self, tmp_path):
        """JSON file containing a dict of {game_id: [preds]} → flattened list."""
        pred_file = tmp_path / "preds.json"
        payload = {
            "0022501001": [{"xgb_pred": 0.62}],
            "0022501002": [{"xgb_pred": 0.44}],
        }
        pred_file.write_text(json.dumps(payload), encoding="utf-8")
        result = load_predictions(str(pred_file))
        assert isinstance(result, list)
        assert len(result) == 2
        game_ids = {r["game_id"] for r in result}
        assert game_ids == {"0022501001", "0022501002"}

    def test_load_predictions_missing_file(self, tmp_path):
        """Non-existent file → empty list."""
        result = load_predictions(str(tmp_path / "nonexistent.json"))
        assert result == []
