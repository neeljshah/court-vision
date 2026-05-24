"""Cycle 63: integration tests for --lineups / --require-starter-lineup in
predict_player.py."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from unittest import mock

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import scripts.predict_player as pp  # noqa: E402


def _starter(pos, name, play_pct=100, injury=None):
    return {"pos": pos, "name": name, "play_pct": play_pct, "injury": injury}


def _lineup_json(games):
    return {"date": "2026-05-24", "fetched_at": "2026-05-24T17:00:00",
            "source": "https://rotowire/x", "games": games}


def _write_tmp(payload):
    fh = tempfile.NamedTemporaryFile("w", delete=False, suffix=".json",
                                       encoding="utf-8")
    json.dump(payload, fh); fh.close()
    return fh.name


def _capture_run(argv, monkeypatch):
    """Run predict_player.main with mocked nba_api boundary, capture stdout."""
    monkeypatch.setattr(pp, "_resolve_player_id", lambda n: 2544)
    monkeypatch.setattr(pp, "_get_playerlog", lambda *a, **k: [])
    monkeypatch.setattr(pp, "build_prediction_row", lambda *a, **k: None)
    captured = []
    def cap(*args, **kwargs):
        captured.append(" ".join(str(a) for a in args))
    with mock.patch.object(sys, "argv", ["predict_player.py"] + argv):
        with mock.patch("builtins.print", side_effect=cap):
            try:
                pp.main()
                exit_code = 0
            except SystemExit as e:
                exit_code = e.code if e.code is not None else 0
    return exit_code, captured


def test_lineups_flag_prints_starter_classification(monkeypatch):
    """Player in lineup at 100% play_pct → 'STARTER' line in output."""
    lu = _lineup_json([{
        "away_team": "OKC", "home_team": "LAL",
        "away_lineup": {"status": "Expected", "starters": []},
        "home_lineup": {"status": "Confirmed", "starters": [
            _starter("SF", "LeBron James", play_pct=100),
        ]},
    }])
    path = _write_tmp(lu)
    try:
        exit_code, captured = _capture_run(
            ["--name", "LeBron James", "--opp", "OKC", "--home",
             "--lineups", path], monkeypatch)
    finally:
        os.unlink(path)
    lineup_line = [c for c in captured if c.startswith("  Lineup:")]
    assert lineup_line, f"no Lineup: line in output: {captured[:6]}"
    assert "STARTER" in lineup_line[0]
    assert "Confirmed" in lineup_line[0]
    assert "100" in lineup_line[0]


def test_lineups_flag_classifies_questionable(monkeypatch):
    lu = _lineup_json([{
        "away_team": "OKC", "home_team": "SAS",
        "away_lineup": {"status": "Expected", "starters": [
            _starter("SF", "Jalen Williams", play_pct=50, injury="Ques"),
        ]},
        "home_lineup": {"status": "Expected", "starters": []},
    }])
    path = _write_tmp(lu)
    try:
        _, captured = _capture_run(
            ["--name", "Jalen Williams", "--opp", "SAS", "--away",
             "--lineups", path], monkeypatch)
    finally:
        os.unlink(path)
    line = [c for c in captured if c.startswith("  Lineup:")][0]
    assert "QUESTIONABLE" in line
    assert "play_pct=50" in line
    assert "inj=Ques" in line


def test_lineups_flag_classifies_bench_for_unknown_player(monkeypatch):
    """LeBron not in OKC/SAS lineups → BENCH classification (lineup data
    exists, player just isn't starting tonight)."""
    lu = _lineup_json([{
        "away_team": "OKC", "home_team": "SAS",
        "away_lineup": {"status": "Expected", "starters": [
            _starter("PG", "Shai Gilgeous-Alexander"),
            _starter("SG", "Luguentz Dort"),
        ]},
        "home_lineup": {"status": "Expected", "starters": [
            _starter("C", "Victor Wembanyama"),
        ]},
    }])
    path = _write_tmp(lu)
    try:
        _, captured = _capture_run(
            ["--name", "LeBron James", "--opp", "OKC", "--home",
             "--lineups", path], monkeypatch)
    finally:
        os.unlink(path)
    line = [c for c in captured if c.startswith("  Lineup:")][0]
    # Not in starter index, index non-empty → BENCH (safe default per
    # src/data/lineups.classify_starter when player_team is unknown).
    assert "BENCH" in line


def test_require_starter_lineup_exits_two_for_bench(monkeypatch):
    """--require-starter-lineup exits 2 when player isn't classified
    starter or questionable."""
    lu = _lineup_json([{
        "away_team": "OKC", "home_team": "SAS",
        "away_lineup": {"status": "Expected", "starters": [
            _starter("PG", "Shai Gilgeous-Alexander"),
        ]},
        "home_lineup": {"status": "Expected", "starters": []},
    }])
    path = _write_tmp(lu)
    try:
        exit_code, captured = _capture_run(
            ["--name", "Random Bench Guy", "--opp", "SAS", "--away",
             "--lineups", path, "--require-starter-lineup"], monkeypatch)
    finally:
        os.unlink(path)
    assert exit_code == 2
    assert any("--require-starter-lineup" in c for c in captured)


def test_require_starter_lineup_does_not_block_questionable(monkeypatch):
    """Questionable IS allowed through (caller chose to predict despite risk)."""
    lu = _lineup_json([{
        "away_team": "OKC", "home_team": "SAS",
        "away_lineup": {"status": "Expected", "starters": [
            _starter("SF", "Jalen Williams", play_pct=50, injury="Ques"),
        ]},
        "home_lineup": {"status": "Expected", "starters": []},
    }])
    path = _write_tmp(lu)
    try:
        exit_code, captured = _capture_run(
            ["--name", "Jalen Williams", "--opp", "SAS", "--away",
             "--lineups", path, "--require-starter-lineup"], monkeypatch)
    finally:
        os.unlink(path)
    # Reach the "no gamelog cached" exit (build_prediction_row mock returns None
    # → exit 2 from that branch). Critically NOT exited by --require-starter-lineup.
    require_skip = [c for c in captured if "--require-starter-lineup set" in c]
    assert require_skip == []


def test_lineups_missing_file_returns_unknown(monkeypatch):
    """If the lineup file doesn't exist, classification is 'unknown' — no crash."""
    _, captured = _capture_run(
        ["--name", "LeBron James", "--opp", "DEN", "--home",
         "--lineups", "/tmp/never_exists_xyz.json"], monkeypatch)
    line = [c for c in captured if c.startswith("  Lineup:")][0]
    assert "UNKNOWN" in line


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
