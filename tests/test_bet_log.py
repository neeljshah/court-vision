"""Tests for compare_to_lines.append_bet_log (cycle 68)."""
from __future__ import annotations

import csv
import os
import sys
import tempfile

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import scripts.compare_to_lines as ctl  # noqa: E402


def _bet(player, stat, line, side, ev=0.05, kelly_pct=2.5, kelly_stake=25.0):
    return {
        "player": player, "stat": stat, "line": line, "model": line + 1.0,
        "edge": 1.0, "side": side, "prob": 0.55, "odds": -110,
        "ev": ev, "kelly_pct": kelly_pct, "kelly_stake": kelly_stake,
    }


def test_append_writes_header_then_rows_on_new_file():
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "bets.csv")
        n = ctl.append_bet_log(out, [_bet("Jokic", "PTS", 28.5, "OVER"),
                                       _bet("Curry", "FG3M", 4.5, "UNDER")],
                                 kelly_bankroll=1000.0)
        assert n == 2
        with open(out) as fh:
            rows = list(csv.DictReader(fh))
        assert len(rows) == 2
        # Schema columns are present and consistent.
        assert set(rows[0].keys()) == {
            "timestamp", "date", "player", "stat", "line", "side", "model",
            "edge", "prob", "odds", "ev_per_dollar", "kelly_pct",
            "kelly_stake", "bankroll",
        }
        assert rows[0]["player"] == "Jokic"
        assert rows[0]["bankroll"] == "1000.00"
        # 2nd row preserves correct columns too.
        assert rows[1]["stat"] == "FG3M"


def test_append_does_not_rewrite_header_on_existing_file():
    """Append mode: bet log should grow over the day's session, header once."""
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "bets.csv")
        ctl.append_bet_log(out, [_bet("Jokic", "PTS", 28.5, "OVER")])
        n2 = ctl.append_bet_log(out, [_bet("LeBron", "AST", 8.5, "OVER")])
        assert n2 == 1
        with open(out) as fh:
            content = fh.read().strip().splitlines()
        # 1 header + 2 data rows
        assert len(content) == 3
        assert content[0].startswith("timestamp,")
        # No second header anywhere
        for line in content[1:]:
            assert not line.startswith("timestamp,")


def test_append_with_no_kelly_bankroll_writes_blank():
    """When --kelly wasn't passed, bankroll column should be empty."""
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "bets.csv")
        ctl.append_bet_log(out, [_bet("Jokic", "PTS", 28.5, "OVER")],
                             kelly_bankroll=None)
        with open(out) as fh:
            row = next(csv.DictReader(fh))
        assert row["bankroll"] == ""


def test_append_creates_parent_dir():
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "deep", "nested", "bets.csv")
        n = ctl.append_bet_log(out, [_bet("X", "PTS", 10.0, "UNDER")])
        assert n == 1
        assert os.path.exists(out)


def test_append_empty_results_writes_only_header():
    """Edge case: empty results list - no rows but header still gets written.
    (Callers should guard with `if results:` but the function shouldn't crash.)"""
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "bets.csv")
        n = ctl.append_bet_log(out, [])
        assert n == 0
        with open(out) as fh:
            content = fh.read().strip().splitlines()
        assert len(content) == 1
        assert content[0].startswith("timestamp,")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
