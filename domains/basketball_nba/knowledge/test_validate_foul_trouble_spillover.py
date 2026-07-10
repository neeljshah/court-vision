"""Per-file test for knowledge.validate_foul_trouble_spillover. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/knowledge/test_validate_foul_trouble_spillover.py -q
"""
from __future__ import annotations

import json

import pandas as pd

from domains.basketball_nba.knowledge import validate_foul_trouble_spillover as vft


def test_is_fga_classifier():
    assert vft._is_fga("MISS Russell 25' 3PT Pullup Jump Shot") == 0
    assert vft._is_fga("Davis 1' Dunk (2 PTS) (Russell 1 AST)") == 2
    assert vft._is_fga("Davis Free Throw 1 of 2 (3 PTS)") is None
    assert vft._is_fga("MISS Jokic Free Throw 1 of 1") is None
    assert vft._is_fga("Davis S.FOUL (P1.T1) (K.Cutler)") is None
    assert vft._is_fga("SUB: Jackson FOR Murray") is None


def test_norm_strips_accents_and_case():
    assert vft._norm("Jokić") == "jokic"
    assert vft._norm("Porter Jr.") == "porter jr."


def _events(rows):
    return [dict(period=1, score="", score_margin="", **r) for r in rows]


def test_game_rows_excludes_the_fouled_starter_from_teammates(tmp_path, monkeypatch):
    """Regression: pbp events carry the SHORT name ('Looney'), boxscore carries
    the FULL name ('Kevon Looney') -- game_rows must match them by suffix, not
    exact equality, both to set the trigger AND to exclude the fouled
    starter's own attempts from the teammates' outcome."""
    monkeypatch.setattr(vft, "PBP_DIR", tmp_path)
    events = _events([
        {"game_clock_sec": 100, "event_type": 6, "event_desc": "Looney S.FOUL (P1.T1)",
         "player_name": "Looney", "team_abbrev": "GSW"},
        {"game_clock_sec": 200, "event_type": 6, "event_desc": "Looney S.FOUL (P2.T2)",
         "player_name": "Looney", "team_abbrev": "GSW"},
        # after CUTOFF_SEC=360: Looney (fouled starter) scores -- must be excluded from "mates"
        {"game_clock_sec": 400, "event_type": 1, "event_desc": "Looney Layup (2 PTS)",
         "player_name": "Looney", "team_abbrev": "GSW"},
        # a teammate's made shot in the same window -- must be counted
        {"game_clock_sec": 420, "event_type": 1, "event_desc": "Curry 3PT Jump Shot (3 PTS)",
         "player_name": "Curry", "team_abbrev": "GSW"},
    ])
    (tmp_path / "pbp_0000000001_p1.json").write_text(json.dumps(events), encoding="utf-8")

    starters = pd.DataFrame([
        {"team": "GSW", "player_name": "Kevon Looney"},
        {"team": "GSW", "player_name": "Stephen Curry"},
    ])
    rows = vft.game_rows("0000000001", starters)
    by_name = {r["starter"]: r for r in rows}

    assert by_name["Kevon Looney"]["trigger"] is True
    # teammates' window excludes Looney's own made shot -- only Curry's counts
    assert by_name["Kevon Looney"]["teammates_fga_rate"] == 1 / 6.0
    assert by_name["Kevon Looney"]["teammates_efficiency"] == 3.0

    assert by_name["Stephen Curry"]["trigger"] is False


def test_run_writes_edge_free_rows_even_with_no_local_pbp(tmp_path, monkeypatch):
    ledger = tmp_path / "validation_ledger.jsonl"
    monkeypatch.setattr(vft, "LEDGER_PATH", ledger)
    monkeypatch.setattr(vft, "PBP_DIR", tmp_path)  # empty dir -> no p1 files on disk
    empty = pd.DataFrame(columns=["game_id", "team", "player_name", "starter", "date"])
    empty["starter"] = empty["starter"].astype(bool)
    monkeypatch.setattr(vft, "load_player_boxscores", lambda: empty)

    rows = vft.run()
    assert len(rows) >= 1
    assert all(r["edge_claimed"] is False and r["sport"] == "basketball_nba" for r in rows)
    assert rows[0]["verdict"] == "NOT_TESTABLE"
    on_disk = [l for l in ledger.read_text(encoding="ascii").splitlines() if l.strip()]
    assert len(on_disk) == len(rows)
