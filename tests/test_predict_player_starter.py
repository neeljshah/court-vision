"""
test_predict_player_starter.py -- Tests for the projected-starter / playing-
time confidence signal added in cycle 46 to scripts/predict_player.py.

All nba_api calls are mocked; tests run fully offline.
"""

from __future__ import annotations

import json
import os
import sys
import time
from unittest import mock

import pytest


PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import predict_player  # noqa: E402


# ── helpers ──────────────────────────────────────────────────────────────────

def _row(start_pos: str = "G", minutes: float = 32.0, date: str = "MAR 01, 2025"):
    """Build a fake playergamelog row matching the nba_api schema."""
    return {
        "GAME_DATE": date,
        "MATCHUP": "DEN vs. LAL",
        "WL": "W",
        "MIN": minutes,
        "PTS": 25,
        "REB": 10,
        "AST": 8,
        "START_POSITION": start_pos,
    }


# ── starter_signal: all-starter case ─────────────────────────────────────────

def test_starter_signal_full_starter():
    rows = [_row(start_pos="G", minutes=34.0) for _ in range(5)]
    sig = predict_player._starter_signal(rows, lookback=5)
    assert sig["starter_rate"] == 1.0
    assert sig["played_rate"] == 1.0
    assert sig["band"] == "full"
    assert "full starter confidence" in sig["message"]


# ── starter_signal: all-bench case ───────────────────────────────────────────

def test_starter_signal_all_bench():
    rows = [_row(start_pos="", minutes=12.0) for _ in range(5)]
    sig = predict_player._starter_signal(rows, lookback=5)
    assert sig["starter_rate"] == 0.0
    # played_rate stays 1.0 because they appeared off the bench (MIN > 0).
    assert sig["played_rate"] == 1.0
    # starter_rate=0 with played_rate=1.0 → falls into "rotation" band
    # (40-79% OR played 60-99% — played_rate is 100% so the OR triggers).
    assert sig["band"] == "rotation"


# ── starter_signal: bench AND missed games → WARNING band ────────────────────

def test_starter_signal_warning_band_when_out_of_rotation():
    """starter_rate=0 + played_rate < 0.6 → WARNING band."""
    rows = [
        _row(start_pos="", minutes=0.0),
        _row(start_pos="", minutes=0.0),
        _row(start_pos="", minutes=0.0),
        _row(start_pos="", minutes=14.0),
        _row(start_pos="", minutes=10.0),
    ]
    sig = predict_player._starter_signal(rows, lookback=5)
    assert sig["starter_rate"] == 0.0
    assert sig["played_rate"] == pytest.approx(0.4)
    assert sig["band"] == "bench"
    assert "WARNING" in sig["message"]


# ── --require-starter exits with code 2 when starter_rate < 0.4 ──────────────

def test_require_starter_exits_two_when_low_starter_rate(monkeypatch, capsys):
    """When --require-starter is set and starter_rate < 0.4, exit(2)."""
    # Mock player roster lookup.
    fake_static = mock.MagicMock()
    fake_static.get_players.return_value = [
        {"id": 99999, "full_name": "Bench Guy"},
    ]
    monkeypatch.setitem(sys.modules, "nba_api.stats.static.players",
                        fake_static)
    # Mock the cached playergamelog fetcher to return all-bench rows.
    bench_rows = [_row(start_pos="", minutes=10.0) for _ in range(5)]
    monkeypatch.setattr(predict_player, "_get_playerlog",
                        lambda pid, season: bench_rows)
    # Mock model + row builders so we don't load real artifacts.
    monkeypatch.setattr(predict_player, "build_prediction_row",
                        lambda *a, **kw: {"f1": 1.0})
    monkeypatch.setattr(predict_player, "predict_pergame",
                        lambda *a, **kw: 12.0)
    monkeypatch.setattr(predict_player, "predict_pergame_quantiles",
                        lambda *a, **kw: {"q10": 5.0, "q50": 12.0, "q90": 20.0})
    monkeypatch.setattr(predict_player, "_player_l5_l10", lambda *a, **kw: {})
    monkeypatch.setattr(sys, "argv",
                        ["predict_player.py", "--name", "Bench Guy",
                         "--opp", "LAL", "--home", "--require-starter"])
    with pytest.raises(SystemExit) as ei:
        predict_player.main()
    assert ei.value.code == 2
    out = capsys.readouterr().out
    assert "require-starter" in out or "starter_rate" in out


# ── cache: writes path on miss, reuses on second call within TTL ─────────────

def test_playerlog_cache_writes_and_reuses(monkeypatch, tmp_path):
    """First call writes the cache file; second call within TTL must NOT
    hit the live fetch."""
    # Redirect cache dir into pytest tmp_path so we don't touch the real one.
    cache_dir = tmp_path / "playerlogs"

    def _fake_cache_path(pid, season):
        cache_dir.mkdir(parents=True, exist_ok=True)
        return str(cache_dir / f"{int(pid)}_{season}.json")
    monkeypatch.setattr(predict_player, "_playerlog_cache_path",
                        _fake_cache_path)

    # Counter so we can prove the live fetch was called exactly once.
    fetch_calls = {"n": 0}
    fake_rows = [_row(start_pos="G", minutes=33.0) for _ in range(5)]

    def _fake_fetch(pid, season):
        fetch_calls["n"] += 1
        return fake_rows
    monkeypatch.setattr(predict_player, "_fetch_playerlog", _fake_fetch)

    # First call → cache miss → fetch + write.
    out1 = predict_player._get_playerlog(203999, "2024-25")
    assert out1 == fake_rows
    assert fetch_calls["n"] == 1
    cache_file = cache_dir / "203999_2024-25.json"
    assert cache_file.exists()
    assert json.loads(cache_file.read_text(encoding="utf-8")) == fake_rows

    # Second call within TTL → cache hit → fetch must NOT be called again.
    out2 = predict_player._get_playerlog(203999, "2024-25")
    assert out2 == fake_rows
    assert fetch_calls["n"] == 1  # still 1


# ── cache expiry: stale file forces re-fetch ─────────────────────────────────

def test_playerlog_cache_expires_after_ttl(monkeypatch, tmp_path):
    """When the cached file is older than the TTL, it must be re-fetched."""
    cache_dir = tmp_path / "playerlogs"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / "111_2024-25.json"
    cache_file.write_text(json.dumps([_row("G", 30.0)]), encoding="utf-8")
    # Backdate the cache file to 1 day ago (TTL is 6h).
    old = time.time() - 24 * 60 * 60
    os.utime(cache_file, (old, old))

    monkeypatch.setattr(predict_player, "_playerlog_cache_path",
                        lambda pid, season: str(cache_file))

    fresh_rows = [_row(start_pos="G", minutes=35.0) for _ in range(3)]
    monkeypatch.setattr(predict_player, "_fetch_playerlog",
                        lambda pid, season: fresh_rows)

    out = predict_player._get_playerlog(111, "2024-25")
    assert out == fresh_rows


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
