"""Per-file test for knowledge.validate_schedule_fatigue. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/knowledge/test_validate_schedule_fatigue.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.basketball_nba.knowledge import _data as kd
from domains.basketball_nba.knowledge import validate_schedule_fatigue as vsf


def _synthetic_pbox(b2b: bool) -> pd.DataFrame:
    """Player-boxscore-shaped rows for 2 teams x N games, home/away alternating.
    b2b=True gives every team a same-day-gap (rest_days==0) game somewhere;
    b2b=False keeps every gap >=1 day (no back-to-backs at all)."""
    rows = []
    gap = 1 if b2b else 3
    start = pd.Timestamp("2024-01-01")
    for g in range(20):
        date = start + pd.Timedelta(days=g * gap)
        gid = "g%03d" % g
        home, away = ("TA", "TB") if g % 2 == 0 else ("TB", "TA")
        for team, is_home, pts in ((home, 1, 110), (away, 0, 100)):
            for p in range(5):
                rows.append({"game_id": gid, "team": team, "date": date, "season": "2023-24",
                             "is_home": is_home, "pts": pts / 5, "min": 30.0})
    return pd.DataFrame(rows)


def test_b2b_rest_penalty_happy_path_returns_well_shaped_row():
    tg = kd.team_game_frame(_synthetic_pbox(b2b=True))
    r = vsf.b2b_rest_penalty(tg)
    assert set(r) >= {"hypothesis", "n", "effect", "p", "verdict", "note"}
    assert r["verdict"] in {"CONFIRMED_LOCAL", "NULL_LOCAL", "NOT_TESTABLE"}
    assert r["n"] > 0


def test_b2b_rest_penalty_with_no_back_to_backs_is_not_testable_not_a_crash():
    """Failure mode: an empty b2b group (no rest_days==0 games at all) must
    verdict NOT_TESTABLE via the NaN-p guard, never raise and never get
    mis-classified as CONFIRMED/NULL off a degenerate empty-group comparison."""
    tg = kd.team_game_frame(_synthetic_pbox(b2b=False))
    r = vsf.b2b_rest_penalty(tg)
    assert r["verdict"] == "NOT_TESTABLE"


def test_run_appends_edge_free_rows_to_the_ledger_path(tmp_path, monkeypatch):
    ledger = tmp_path / "validation_ledger.jsonl"
    monkeypatch.setattr(vsf, "LEDGER_PATH", ledger)
    monkeypatch.setattr(vsf, "load_player_boxscores", lambda: _synthetic_pbox(b2b=True))
    rows = vsf.run()
    assert len(rows) == 3
    assert all(r["edge_claimed"] is False and r["sport"] == "basketball_nba" for r in rows)
    on_disk = [r for r in ledger.read_text(encoding="ascii").splitlines() if r.strip()]
    assert len(on_disk) == 3
