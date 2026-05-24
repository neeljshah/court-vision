"""Tests for predict_player.py --save (cycle 49).

Schema MUST mirror scripts/predict_slate.py save_predictions_csv so that
single-player and slate runs append to the same daily ledger and a future
backtest can join on (date, player_id, stat) without per-source branching.
"""
from __future__ import annotations

import csv
import os
import sys
import tempfile

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import scripts.predict_player as pp  # noqa: E402


def _preds():
    return {
        "pts": 28.4, "reb": 12.1, "ast": 9.8,
        "fg3m": 1.5, "stl": 0.8, "blk": 0.4, "tov": 3.1,
    }


def test_append_writes_header_then_rows():
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "preds.csv")
        n = pp.append_predictions_csv(out, 203999, "Nikola Jokic", "LAL",
                                       is_home=True, stat_preds=_preds())
        assert n == 7
        with open(out) as fh:
            rows = list(csv.DictReader(fh))
        assert len(rows) == 7
        # Schema parity with predict_slate.save_predictions_csv
        # Cycle 80: added lineup_status, lineup_class, play_pct, injury_status
        assert set(rows[0].keys()) == {
            "date", "game_id", "player_id", "player",
            "team", "opp", "venue", "stat", "pred",
            "lineup_status", "lineup_class", "play_pct", "injury_status",
        }
        assert {r["stat"] for r in rows} == set(pp.STATS)
        assert all(r["venue"] == "home" for r in rows)
        assert all(r["opp"] == "LAL" for r in rows)
        assert all(r["player_id"] == "203999" for r in rows)


def test_append_does_not_rewrite_header_on_existing_file():
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "preds.csv")
        # Two separate appends — slate run + single-player run on the same date.
        pp.append_predictions_csv(out, 203999, "Nikola Jokic", "LAL",
                                   is_home=True, stat_preds=_preds())
        n2 = pp.append_predictions_csv(out, 2544, "LeBron James", "DEN",
                                        is_home=False, stat_preds=_preds())
        assert n2 == 7
        with open(out) as fh:
            content = fh.read().strip().splitlines()
        # 1 header + 14 rows. Header must NOT repeat between players.
        assert len(content) == 15
        assert content[0].startswith("date,game_id,")
        # Second run rows start at line 8 (header + first 7 rows)
        for line in content[1:]:
            assert not line.startswith("date,")


def test_append_skips_missing_stats():
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "preds.csv")
        partial = {"pts": 10.0, "reb": 4.0}  # only 2 of 7 stats
        n = pp.append_predictions_csv(out, 99, "X. Player", "LAL",
                                       is_home=False, stat_preds=partial)
        assert n == 2
        with open(out) as fh:
            rows = list(csv.DictReader(fh))
        assert {r["stat"] for r in rows} == {"pts", "reb"}
        assert all(r["venue"] == "away" for r in rows)


def test_append_creates_parent_dir():
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "deep", "nested", "preds.csv")
        n = pp.append_predictions_csv(out, 99, "X. Player", "LAL",
                                       is_home=True, stat_preds=_preds())
        assert n == 7
        assert os.path.exists(out)


# ─── cycle 80: context columns ───────────────────────────────────────────────

def test_append_writes_context_columns_when_provided():
    """When the CLI knows lineup + injury context, the ledger captures it."""
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "preds.csv")
        n = pp.append_predictions_csv(
            out, 203999, "Nikola Jokic", "LAL",
            is_home=True, stat_preds=_preds(),
            lineup_status="Expected", lineup_class="questionable",
            play_pct="50", injury_status="QUESTIONABLE",
        )
        assert n == 7
        with open(out) as fh:
            row = next(csv.DictReader(fh))
    assert row["lineup_status"] == "Expected"
    assert row["lineup_class"] == "questionable"
    assert row["play_pct"] == "50"
    assert row["injury_status"] == "QUESTIONABLE"


def test_append_defaults_context_columns_to_blank():
    """Cycle 49 callers that don't pass context still work — blank values."""
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "preds.csv")
        pp.append_predictions_csv(out, 99, "X. Player", "LAL",
                                    is_home=True, stat_preds=_preds())
        with open(out) as fh:
            row = next(csv.DictReader(fh))
    for col in ("lineup_status", "lineup_class", "play_pct", "injury_status"):
        assert row[col] == ""


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
