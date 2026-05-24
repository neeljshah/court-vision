"""Tests for scripts/fetch_dk_props.py (cycle 59 — DraftKings → canonical CSV)."""
from __future__ import annotations

import csv
import os
import sys
import tempfile

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import scripts.fetch_dk_props as fdp  # noqa: E402


def _mock_prop(name, prop_type, line, over=-115, under=-105, book="draftkings"):
    return {
        "player_name": name, "prop_type": prop_type, "line": line,
        "over_odds": over, "under_odds": under, "book": book,
        "fetched_at": "2026-05-24T17:00:00",
    }


def test_collect_props_maps_dk_prop_types_to_canonical(monkeypatch):
    """DK 'points'/'rebounds'/'threes' → 'pts'/'reb'/'fg3m'."""
    def fake_get(book):
        assert book == "draftkings"
        return [
            _mock_prop("Nikola Jokic", "points", 28.5),
            _mock_prop("Nikola Jokic", "rebounds", 11.5),
            _mock_prop("Stephen Curry", "threes", 4.5),
        ]
    monkeypatch.setattr(fdp, "get_current_props", fake_get)
    out = fdp.collect_props(["draftkings"])
    stats = sorted(p["stat"] for p in out)
    assert stats == ["fg3m", "pts", "reb"]


def test_collect_props_skips_unknown_prop_types(monkeypatch):
    """DK exposes other props (PRA combos, doubles) — those map to nothing."""
    def fake_get(book):
        return [
            _mock_prop("LeBron James", "points", 25.5),
            _mock_prop("LeBron James", "pra_combo", 47.5),  # not in _PROP_MAP
            _mock_prop("LeBron James", "double_double", 1.5),
        ]
    monkeypatch.setattr(fdp, "get_current_props", fake_get)
    out = fdp.collect_props(["draftkings"])
    assert [p["stat"] for p in out] == ["pts"]


def test_collect_props_dedups_across_books(monkeypatch):
    """If both books have the same (player, stat, line) → first book wins."""
    by_book = {
        "draftkings": [_mock_prop("Nikola Jokic", "points", 28.5, book="draftkings")],
        "fanduel":    [_mock_prop("Nikola Jokic", "points", 28.5, book="fanduel"),
                       _mock_prop("Nikola Jokic", "points", 29.5, book="fanduel")],
    }
    monkeypatch.setattr(fdp, "get_current_props", lambda book: by_book.get(book, []))
    out = fdp.collect_props(["draftkings", "fanduel"])
    # 3 input rows → 2 unique (DK 28.5 + FD 29.5).
    assert len(out) == 2
    # Jokic 28.5 came from DK first; that's the source kept.
    rec = [p for p in out if p["line"] == 28.5][0]
    assert rec["book"] == "draftkings"


def test_write_canonical_schema_matches_compare_to_lines():
    """CSV header must exactly match what compare_to_lines.py reads."""
    props = [
        {"player": "Nikola Jokic", "stat": "pts", "line": 28.5,
         "over_odds": -115, "under_odds": -105, "book": "draftkings"},
        {"player": "Stephen Curry", "stat": "fg3m", "line": 4.5,
         "over_odds": -110, "under_odds": -110, "book": "draftkings"},
    ]
    # Map Jokic to team 1610612743 (DEN), Curry to 1610612744 (GSW)
    team_lookup = {
        1610612743: {"opp": "LAL", "venue": "home"},
        1610612744: {"opp": "BOS", "venue": "away"},
    }
    def resolve(name):
        return {"Nikola Jokic": 1610612743, "Stephen Curry": 1610612744}.get(name, 0)
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "tonight.csv")
        n = fdp.write_canonical(props, team_lookup, resolve, out)
        assert n == 2
        with open(out) as fh:
            rows = list(csv.DictReader(fh))
        assert set(rows[0].keys()) == {
            "player", "opp", "venue", "stat", "line", "over_odds", "under_odds",
        }
        jokic = [r for r in rows if r["player"] == "Nikola Jokic"][0]
        assert jokic["opp"] == "LAL"
        assert jokic["venue"] == "home"
        assert jokic["line"] == "28.5"
        curry = [r for r in rows if r["player"] == "Stephen Curry"][0]
        assert curry["venue"] == "away"


def test_write_canonical_handles_unknown_player_team():
    """If a player isn't on tonight's slate, opp blank + default venue=home."""
    props = [{"player": "Mystery Guy", "stat": "pts", "line": 10.0,
              "over_odds": -110, "under_odds": -110, "book": "draftkings"}]
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "out.csv")
        fdp.write_canonical(props, {1: {"opp": "X", "venue": "home"}},
                              resolve_team_fn=lambda n: 0,    # never resolves
                              out_path=out)
        with open(out) as fh:
            row = next(csv.DictReader(fh))
        assert row["opp"] == ""
        assert row["venue"] == "home"


def test_write_canonical_with_empty_team_lookup_skips_join():
    """Empty team_lookup → never calls resolve_team_fn, output rows have blank opp."""
    props = [{"player": "Nikola Jokic", "stat": "pts", "line": 28.5,
              "over_odds": -110, "under_odds": -110, "book": "draftkings"}]
    calls = []
    def resolve(name):
        calls.append(name)
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "out.csv")
        fdp.write_canonical(props, {}, resolve, out)
        # No team_lookup → resolve_team_fn must not be called (would waste API hits).
        assert calls == []
        with open(out) as fh:
            row = next(csv.DictReader(fh))
        assert row["opp"] == ""


def test_write_canonical_creates_parent_dir():
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "deep", "nested", "out.csv")
        fdp.write_canonical([], {}, lambda n: 0, out)
        assert os.path.exists(out)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
