"""
test_predict_player.py -- Tests for the scripts/predict_player.py CLI.

The CLI takes --name (or --pid), --opp, --home/--away, --rest, and prints
seven stat predictions + 80% intervals + L5/L10 baselines + bet
recommendation. All external dependencies (nba_api roster, model loader,
quantile loader, gamelog cache) are mocked so the suite runs offline.
"""

from __future__ import annotations

import importlib
import os
import sys
from unittest import mock

import pytest


PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import predict_player  # noqa: E402


# ── name lookup ──────────────────────────────────────────────────────────────

def test_resolve_player_id_is_diacritic_insensitive(monkeypatch):
    """'Nikola Jokic' (ASCII) must resolve the player whose canonical
    full_name is 'Nikola Jokić' (with diacritic)."""
    fake_players = [
        {"id": 203999, "full_name": "Nikola Jokić"},
        {"id": 2544, "full_name": "LeBron James"},
    ]
    fake_static = mock.MagicMock()
    fake_static.get_players.return_value = fake_players
    fake_nba_api_stats_static = mock.MagicMock(players=fake_static)
    fake_nba_api_stats = mock.MagicMock(static=fake_nba_api_stats_static)
    fake_nba_api = mock.MagicMock(stats=fake_nba_api_stats)
    monkeypatch.setitem(sys.modules, "nba_api", fake_nba_api)
    monkeypatch.setitem(sys.modules, "nba_api.stats", fake_nba_api_stats)
    monkeypatch.setitem(sys.modules, "nba_api.stats.static",
                        fake_nba_api_stats_static)
    monkeypatch.setitem(sys.modules, "nba_api.stats.static.players",
                        fake_static)

    pid = predict_player._resolve_player_id("Nikola Jokic")
    assert pid == 203999


def test_resolve_player_id_returns_none_when_not_found(monkeypatch):
    fake_static = mock.MagicMock()
    fake_static.get_players.return_value = [
        {"id": 2544, "full_name": "LeBron James"},
    ]
    monkeypatch.setitem(sys.modules, "nba_api.stats.static.players",
                        fake_static)
    assert predict_player._resolve_player_id("Totally Made Up") is None


# ── venue + rest defaults via argparse ───────────────────────────────────────

def _run_main(monkeypatch, argv, predict_value=20.0, qint=None,
              build_row_returns=None, l5_value=None, resolve_pid=12345):
    """Shared harness: patch out all external deps, then call main()."""
    # Mock nba_api roster.
    fake_static = mock.MagicMock()
    fake_static.get_players.return_value = [
        {"id": resolve_pid, "full_name": "Nikola Jokić"},
    ]
    monkeypatch.setitem(sys.modules, "nba_api.stats.static.players",
                        fake_static)
    monkeypatch.setattr(predict_player, "build_prediction_row",
                        lambda *a, **kw: (build_row_returns
                                          if build_row_returns is not None
                                          else {"f1": 1.0}))
    monkeypatch.setattr(predict_player, "predict_pergame",
                        lambda *a, **kw: predict_value)
    monkeypatch.setattr(predict_player, "predict_pergame_quantiles",
                        lambda *a, **kw: (qint
                                          if qint is not None
                                          else {"q10": 10.0, "q50": 20.0,
                                                "q90": 30.0}))
    if l5_value is not None:
        monkeypatch.setattr(predict_player, "_player_l5_l10",
                            lambda *a, **kw: l5_value)
    else:
        monkeypatch.setattr(predict_player, "_player_l5_l10",
                            lambda *a, **kw: {})
    monkeypatch.setattr(sys, "argv", argv)
    predict_player.main()


def test_home_away_mutually_exclusive(monkeypatch, capsys):
    """--home and --away together must raise SystemExit via argparse."""
    monkeypatch.setattr(sys, "argv",
                        ["predict_player.py", "--name", "Nikola Jokic",
                         "--opp", "LAL", "--home", "--away"])
    with pytest.raises(SystemExit):
        predict_player.main()


def test_default_venue_is_home(monkeypatch, capsys):
    """When neither --home nor --away is passed, the printed header should
    say 'home' (default is home)."""
    _run_main(monkeypatch, ["predict_player.py", "--name", "Nikola Jokic",
                            "--opp", "LAL"])
    out = capsys.readouterr().out
    assert "home vs LAL" in out


def test_rest_defaults_to_2(monkeypatch, capsys):
    """When --rest is omitted, the printed header says rest=2.0d."""
    _run_main(monkeypatch, ["predict_player.py", "--name", "Nikola Jokic",
                            "--opp", "LAL", "--home"])
    out = capsys.readouterr().out
    assert "rest=2.0d" in out


# ── bet recommendation appears only when |edge| > 0.5 ────────────────────────

def test_bet_appears_only_when_edge_exceeds_half_unit(monkeypatch, capsys):
    """Predictor returns 25.0; L5 returns 24.0 (edge=+1.0 > 0.5) → OVER line."""
    l5 = {f"l5_{s}": 24.0 for s in ("pts", "reb", "ast", "fg3m", "stl",
                                     "blk", "tov")}
    l5.update({f"l10_{s}": 24.0 for s in ("pts", "reb", "ast", "fg3m", "stl",
                                          "blk", "tov")})
    _run_main(monkeypatch,
              ["predict_player.py", "--name", "Nikola Jokic",
               "--opp", "LAL", "--home"],
              predict_value=25.0,
              l5_value=l5)
    out = capsys.readouterr().out
    # +1.00 edge per stat → "OVER" appears
    assert "OVER" in out
    assert "(no edge)" not in out


def test_no_bet_when_edge_within_half_unit(monkeypatch, capsys):
    """Predictor=25.0, L5=24.8 (edge=+0.2 < 0.5) → '(no edge)'."""
    l5 = {f"l5_{s}": 24.8 for s in ("pts", "reb", "ast", "fg3m", "stl",
                                     "blk", "tov")}
    l5.update({f"l10_{s}": 24.8 for s in ("pts", "reb", "ast", "fg3m", "stl",
                                          "blk", "tov")})
    _run_main(monkeypatch,
              ["predict_player.py", "--name", "Nikola Jokic",
               "--opp", "LAL", "--home"],
              predict_value=25.0,
              l5_value=l5)
    out = capsys.readouterr().out
    assert "(no edge)" in out
    # Neither OVER nor UNDER should be recommended for this edge size
    for line in out.splitlines():
        if "OVER" in line or "UNDER" in line:
            pytest.fail(f"unexpected bet recommendation when |edge|<0.5: {line}")


# ── player-not-found gives clean SystemExit ─────────────────────────────────

def test_unknown_player_exits_cleanly(monkeypatch, capsys):
    """If _resolve_player_id returns None the script must SystemExit(1)
    with a 'could not resolve' message — never a traceback."""
    fake_static = mock.MagicMock()
    fake_static.get_players.return_value = []
    monkeypatch.setitem(sys.modules, "nba_api.stats.static.players",
                        fake_static)
    monkeypatch.setattr(sys, "argv",
                        ["predict_player.py", "--name", "Ghost Player",
                         "--opp", "LAL", "--home"])
    with pytest.raises(SystemExit) as ei:
        predict_player.main()
    assert ei.value.code == 1
    out = capsys.readouterr().out
    assert "could not resolve" in out


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
