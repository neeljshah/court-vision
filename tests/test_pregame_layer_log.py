"""Tests for src/prediction/pregame_layer_log.py."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def tmp_log(tmp_path, monkeypatch):
    """Point the logger at a tmp path and clear flags so each test is hermetic."""
    log_path = tmp_path / "layers.jsonl"
    monkeypatch.setenv("CV_LAYER_LOG_PATH", str(log_path))
    monkeypatch.delenv("CV_LAYER_LOG", raising=False)
    # the module caches nothing — env reads happen per-call — but reimport
    # ensures any test-local monkeypatching is honored.
    import importlib
    import src.prediction.pregame_layer_log as m
    importlib.reload(m)
    return log_path, m


class TestLogger:
    def test_default_off_is_strict_noop(self, tmp_log):
        log_path, m = tmp_log
        assert m.is_enabled() is False
        ok = m.log(date="2026-06-01", player_id=1, stat="pts",
                   line=22.5, base=23.7)
        assert ok is False
        assert not log_path.exists()

    def test_flag_on_writes_row(self, tmp_log, monkeypatch):
        log_path, m = tmp_log
        monkeypatch.setenv("CV_LAYER_LOG", "1")
        ok = m.log(date="2026-06-01", player_id=42, stat="reb",
                   line=7.5, base=8.1, after_cal=7.9, after_live=7.95,
                   vac_share=0.12, game_total=228.5, game_spread=4.5,
                   opp="DEN", over_odds=-110, under_odds=-110)
        assert ok is True
        assert log_path.exists()
        rows = [json.loads(l) for l in log_path.read_text(encoding="utf-8").splitlines()]
        assert len(rows) == 1
        r = rows[0]
        assert r["player_id"] == 42
        assert r["stat"] == "reb"
        assert r["base"] == 8.1
        assert r["after_cal"] == 7.9
        assert r["after_live"] == 7.95
        assert r["vac_share"] == 0.12
        assert r["opp"] == "DEN"
        assert r["ts"]  # timestamp populated

    def test_force_overrides_flag(self, tmp_log):
        log_path, m = tmp_log
        # flag not set, but force=True still writes
        ok = m.log(date="2026-06-01", player_id=1, stat="pts",
                   line=22.5, base=23.7, force=True)
        assert ok is True
        assert log_path.exists()

    def test_append_does_not_clobber(self, tmp_log, monkeypatch):
        log_path, m = tmp_log
        monkeypatch.setenv("CV_LAYER_LOG", "1")
        for pid in (1, 2, 3):
            m.log(date="2026-06-01", player_id=pid, stat="pts",
                  line=20.5, base=22.0)
        rows = [json.loads(l) for l in log_path.read_text(encoding="utf-8").splitlines()]
        assert [r["player_id"] for r in rows] == [1, 2, 3]

    def test_writes_lowercase_stat(self, tmp_log, monkeypatch):
        log_path, m = tmp_log
        monkeypatch.setenv("CV_LAYER_LOG", "1")
        m.log(date="2026-06-01", player_id=1, stat="PTS",
              line=22.5, base=23.7)
        rec = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
        assert rec["stat"] == "pts"

    def test_none_optional_fields_pass_through(self, tmp_log, monkeypatch):
        log_path, m = tmp_log
        monkeypatch.setenv("CV_LAYER_LOG", "1")
        m.log(date="2026-06-01", player_id=1, stat="pts",
              line=22.5, base=23.7)  # no after_cal / after_live / vac_share
        rec = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
        assert rec["after_cal"] is None
        assert rec["after_live"] is None
        assert rec["vac_share"] is None
        assert rec["game_total"] is None

    def test_logger_swallows_io_errors(self, tmp_log, monkeypatch):
        """If the disk write fails the logger must return False, not raise."""
        log_path, m = tmp_log
        monkeypatch.setenv("CV_LAYER_LOG", "1")
        # point CV_LAYER_LOG_PATH at a directory that exists but is unwritable
        # (simpler: monkeypatch open to throw)
        def _boom(*a, **k):
            raise OSError("disk full")
        with patch("src.prediction.pregame_layer_log.open", _boom, create=True):
            ok = m.log(date="2026-06-01", player_id=1, stat="pts",
                       line=22.5, base=23.7)
        assert ok is False  # never raises
