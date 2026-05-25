"""tests/test_recommendation_strategy_integration.py -- cycle 104c (loop 5).

Wires recommend_endQ2_bets + compare_to_lines to ab_strategy: every row
in either recommender's output carries a strategy tag, and the emitted
place_bet command parses cleanly under place_bet.py's argparse so the
operator can copy/paste without edits.
"""
from __future__ import annotations

import argparse
import importlib
import os
import shlex
import subprocess
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)


@pytest.fixture
def ab_env(monkeypatch, tmp_path):
    """Isolated ab_strategy + pnl_ledger writing into tmp_path."""
    import src.betting.pnl_ledger as L
    importlib.reload(L)
    monkeypatch.setattr(L, "LEDGER_CSV",   str(tmp_path / "pnl_ledger.csv"))
    monkeypatch.setattr(L, "BANKROLL_CSV", str(tmp_path / "pnl_bankroll.csv"))
    monkeypatch.setattr(L, "LOCK_PATH",    str(tmp_path / "pnl_ledger.csv.lock"))

    import src.betting.ab_strategy as AB
    importlib.reload(AB)
    monkeypatch.setattr(AB, "_pnl", L)
    monkeypatch.setattr(AB, "STRATEGIES_CSV", str(tmp_path / "ab_strategies.csv"))

    import src.betting.recommendation as R
    importlib.reload(R)
    return AB, L, R


# 1
def test_recommend_endq2_has_strategy_flag(ab_env):
    """recommend_endQ2_bets.main accepts --strategy and --register flags."""
    import scripts.recommend_endQ2_bets as rec
    importlib.reload(rec)
    # Smoke: argparse should accept the flags without raising SystemExit.
    out = subprocess.run(
        [sys.executable, os.path.join(PROJECT_DIR, "scripts",
                                       "recommend_endQ2_bets.py"),
         "--date", "2099-01-01", "--dry-run",
         "--strategy", "endQ2_test"],
        capture_output=True, text=True, cwd=PROJECT_DIR,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert out.returncode == 0, out.stderr
    assert "strategy=endQ2_test" in out.stdout


# 2
def test_auto_register_creates_strategy_entry(ab_env):
    AB, _, R = ab_env
    assert AB.list_strategies() == []
    rec = R.ensure_strategy_registered("endQ2_auto", bankroll=1000.0,
                                        max_bet_pct=0.05)
    assert rec["strategy"] == "endQ2_auto"
    names = [r["strategy"] for r in AB.list_strategies()]
    assert "endQ2_auto" in names
    # Idempotent: second call returns the same record, doesn't add another.
    R.ensure_strategy_registered("endQ2_auto")
    assert [r["strategy"] for r in AB.list_strategies()].count("endQ2_auto") == 1


# 3
def test_place_bet_command_parses_via_argparse(ab_env):
    _, _, R = ab_env
    row = {
        "player": "Nikola Jokic", "team": "DEN", "stat": "reb",
        "line": 11.5, "side": "OVER", "projection": 13.07,
        "edge": 1.57, "kelly_pct": 5.42, "kelly_stake": 54.20,
        "game_id": "0022500123", "player_id": 203999,
    }
    cmd = R.to_place_bet_command(row, "endQ2_auto")
    assert "--strategy endQ2_auto" in cmd
    # Drop the leading "python scripts/place_bet.py" and parse with the
    # actual place_bet.py argparse, mirroring its CLI definition.
    tokens = shlex.split(cmd)[2:]
    ap = argparse.ArgumentParser()
    ap.add_argument("--game",   required=True)
    ap.add_argument("--player", required=True)
    ap.add_argument("--stat",   required=True)
    ap.add_argument("--line",   required=True, type=float)
    ap.add_argument("--side",   required=True)
    ap.add_argument("--book",   required=True)
    ap.add_argument("--odds",   required=True, type=int)
    ap.add_argument("--stake",  required=True, type=float)
    ap.add_argument("--strategy", default=None)
    ap.add_argument("--team", default=None)
    ap.add_argument("--player-id", default=None, dest="player_id")
    ap.add_argument("--model-pred", type=float, default=None, dest="model_pred")
    ap.add_argument("--kelly-pct",  type=float, default=None, dest="kelly_pct")
    ns = ap.parse_args(tokens)
    assert ns.strategy == "endQ2_auto"
    assert ns.player == "Nikola Jokic"
    assert ns.line == 11.5
    assert ns.side == "OVER"
    assert ns.stake > 0


# 4
def test_format_recommendation_row_consistent_shape(ab_env):
    _, _, R = ab_env
    row = {"player": "Player A", "stat": "ast", "line": 5.5,
           "side": "OVER", "projection": 7.2, "edge": 1.7,
           "kelly_pct": 4.2, "kelly_stake": 42.0,
           "ev_per_dollar": 0.08}
    s = R.format_recommendation_row(row, "pregame_auto")
    assert "Player A" in s
    assert "AST" in s
    assert "OVER" in s
    assert "strategy=pregame_auto" in s
    # Missing required field -> ValueError
    with pytest.raises(ValueError):
        R.format_recommendation_row({"player": "X"}, "pregame_auto")


# 5
def test_compare_to_lines_help_advertises_strategy_flag():
    """compare_to_lines.py --help mentions --strategy + --register-strategy."""
    out = subprocess.run(
        [sys.executable, os.path.join(PROJECT_DIR, "scripts",
                                       "compare_to_lines.py"), "--help"],
        capture_output=True, text=True, cwd=PROJECT_DIR,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert out.returncode == 0, out.stderr
    assert "--strategy" in out.stdout
    assert "--register-strategy" in out.stdout
