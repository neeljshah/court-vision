"""Tests for scripts/predict_slate.py — the --save CSV writer.

The slate CLI itself hits nba_api at runtime, so the live happy-path is not
exercised here. These tests target the CSV-writing branch added in cycle 47:
input → canonical row layout, default vs explicit path, and one-row-per-stat
expansion. STATS comes from prop_pergame and must stay in sync.
"""
from __future__ import annotations

import csv
import os
import sys
import tempfile
import unittest
from unittest import mock

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# Import after sys.path append so module-level nba_api header patch runs.
import scripts.predict_slate as ps  # noqa: E402


def _fake_game():
    return {
        "game_id":     "0022400999",
        "home_id":     1610612747,
        "away_id":     1610612743,
        "home_abbrev": "LAL",
        "away_abbrev": "DEN",
    }


def _fake_row(name, pid, team, preds=None):
    preds = preds if preds is not None else {
        "pts": 25.3, "reb": 5.1, "ast": 7.4, "fg3m": 2.1,
        "stl": 1.0, "blk": 0.4, "tov": 2.6,
    }
    return {"player_id": pid, "name": name, "team": team, "preds": preds}


def test_save_predictions_csv_writes_one_row_per_stat():
    g = _fake_game()
    home_rows = [_fake_row("LeBron James", 2544, "LAL")]
    away_rows = [_fake_row("Nikola Jokic", 203999, "DEN")]
    per_game = [(g, home_rows, away_rows)]

    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "out.csv")
        n = ps.save_predictions_csv(out, "2026-05-24", [g], per_game)
        # 2 players × 7 stats = 14
        assert n == 14
        with open(out) as fh:
            rows = list(csv.DictReader(fh))
    assert len(rows) == 14
    assert {r["stat"] for r in rows} == set(ps.STATS)
    lebron = [r for r in rows if r["player"] == "LeBron James"]
    assert {r["venue"] for r in lebron} == {"home"}
    assert {r["opp"] for r in lebron} == {"DEN"}
    jokic = [r for r in rows if r["player"] == "Nikola Jokic"]
    assert {r["venue"] for r in jokic} == {"away"}
    assert {r["opp"] for r in jokic} == {"LAL"}


def test_save_skips_missing_stats():
    g = _fake_game()
    # Player only has PTS predicted — REB/AST/... missing in the preds dict.
    rows = [_fake_row("X. Player", 99, "LAL", preds={"pts": 10.0})]
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "out.csv")
        n = ps.save_predictions_csv(out, "2026-05-24", [g], [(g, rows, [])])
        assert n == 1
        with open(out) as fh:
            rows_out = list(csv.DictReader(fh))
    assert len(rows_out) == 1
    assert rows_out[0]["stat"] == "pts"
    assert rows_out[0]["pred"] == "10.0000"


def test_save_creates_parent_dir():
    g = _fake_game()
    rows = [_fake_row("X. Player", 99, "LAL")]
    with tempfile.TemporaryDirectory() as tmp:
        nested = os.path.join(tmp, "deep", "nested", "out.csv")
        n = ps.save_predictions_csv(nested, "2026-05-24", [g], [(g, rows, [])])
        assert n == 7
        assert os.path.exists(nested)


def test_save_handles_empty_per_game():
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "out.csv")
        n = ps.save_predictions_csv(out, "2026-05-24", [], [])
        assert n == 0
        # File is created with just the header row.
        with open(out) as fh:
            content = fh.read().strip().splitlines()
        assert len(content) == 1
        assert content[0].startswith("date,game_id,")


# ─── cycle 80: enriched context columns ──────────────────────────────────────

def test_save_includes_lineup_and_injury_context_when_provided():
    """When the caller passes starter_idx + injury data, the ledger captures
    lineup_status, lineup_class, play_pct, and injury_status per player."""
    g = _fake_game()
    home_rows = [_fake_row("LeBron James", 2544, "LAL")]
    away_rows = [_fake_row("Nikola Jokic", 203999, "DEN")]
    per_game = [(g, home_rows, away_rows)]

    starter_idx = {
        "lebron james": {"team": "LAL", "pos": "SF", "play_pct": 100,
                          "injury": None, "lineup_status": "Confirmed"},
        "nikola jokic": {"team": "DEN", "pos": "C", "play_pct": 50,
                          "injury": "Ques", "lineup_status": "Expected"},
    }
    soft_inj = {"nikola jokic": "QUESTIONABLE"}

    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "out.csv")
        n = ps.save_predictions_csv(
            out, "2026-05-24", [g], per_game,
            starter_idx=starter_idx, soft_inj=soft_inj,
        )
        assert n == 14
        with open(out) as fh:
            rows = list(csv.DictReader(fh))
    # New columns are present in every row.
    for r in rows:
        assert "lineup_status" in r
        assert "lineup_class" in r
        assert "play_pct" in r
        assert "injury_status" in r
    lebron = [r for r in rows if r["player"] == "LeBron James"][0]
    assert lebron["lineup_status"] == "Confirmed"
    assert lebron["lineup_class"] == "starter"
    assert lebron["play_pct"] == "100"
    assert lebron["injury_status"] == ""    # not in soft_inj
    jokic = [r for r in rows if r["player"] == "Nikola Jokic"][0]
    assert jokic["lineup_status"] == "Expected"
    assert jokic["lineup_class"] == "questionable"   # play_pct < 80
    assert jokic["play_pct"] == "50"
    assert jokic["injury_status"] == "QUESTIONABLE"


def test_save_leaves_context_columns_blank_when_no_data():
    """Backwards-compat: cycle 47 callers that pass no starter_idx / injuries
    still get a valid CSV — context columns just write blank."""
    g = _fake_game()
    home_rows = [_fake_row("LeBron James", 2544, "LAL")]
    per_game = [(g, home_rows, [])]
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "out.csv")
        ps.save_predictions_csv(out, "2026-05-24", [g], per_game)
        with open(out) as fh:
            rows = list(csv.DictReader(fh))
    # New columns exist in the header but values are empty strings.
    for r in rows:
        assert r["lineup_status"] == ""
        assert r["lineup_class"] == ""
        assert r["play_pct"] == ""
        assert r["injury_status"] == ""


def test_save_strips_lineup_tag_before_context_lookup():
    """cycle 64 _tag_lineup may prepend ' [BENCH]' to the name before save.
    Cycle 80's lookup must strip that suffix so the starter_idx key matches."""
    g = _fake_game()
    tagged = _fake_row("Austin Reaves [BENCH]", 1630559, "LAL")
    per_game = [(g, [tagged], [])]
    # Empty starter_idx but inj for the un-tagged name should still be found.
    unav = {"austin reaves": "OUT"}
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "out.csv")
        ps.save_predictions_csv(out, "2026-05-24", [g], per_game, unav_inj=unav)
        with open(out) as fh:
            rows = list(csv.DictReader(fh))
    assert rows
    # Saved 'player' column is the de-tagged name.
    assert rows[0]["player"] == "Austin Reaves"
    # Injury lookup matched even though caller's row name had the tag.
    assert rows[0]["injury_status"] == "OUT"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
