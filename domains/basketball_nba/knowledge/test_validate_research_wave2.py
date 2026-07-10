"""Per-file test for knowledge.validate_research_wave2. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/knowledge/test_validate_research_wave2.py -q
"""
from __future__ import annotations

import json

import pandas as pd

from domains.basketball_nba.knowledge import validate_research_wave2 as vrw2


def test_self_check():
    vrw2._self_check()


def test_team_slot_map_requires_exactly_two_teams():
    events = [{"period": 1, "game_clock_sec": 0, "team_abbrev": "BOS", "score": "0-0"}]
    assert vrw2._team_slot_map(events) is None  # only one team seen


def test_resolve_team_handles_allcaps_pbp_nickname_forms():
    assert vrw2.resolve_team("TRAIL BLAZERS") == "POR"
    assert vrw2.resolve_team("PACERS") == "IND"
    assert vrw2.resolve_team("Fictitious Squad") is None


def test_game_samples_drops_windows_truncated_below_floor(tmp_path, monkeypatch):
    """A timeout at game_clock_sec=20 has only a 20s before-window (<MIN_WINDOW_SEC=60)
    -- must be dropped, not padded or biased."""
    monkeypatch.setattr(vrw2, "PBP_DIR", tmp_path)
    events = [
        {"period": 1, "game_clock_sec": 0, "event_desc": "Start", "team_abbrev": "", "score": "0-0"},
        {"period": 1, "game_clock_sec": 5, "event_desc": "Smart makes (2 PTS)", "team_abbrev": "BOS", "score": "2-0"},
        {"period": 1, "game_clock_sec": 20, "event_desc": "CELTICS Timeout: Regular", "team_abbrev": "", "score": "2-0"},
        {"period": 1, "game_clock_sec": 250, "event_desc": "Smart makes (2 PTS)", "team_abbrev": "BOS", "score": "4-0"},
        {"period": 1, "game_clock_sec": 400, "event_desc": "76ers Timeout: Regular", "team_abbrev": "", "score": "4-0"},
        {"period": 1, "game_clock_sec": 500, "event_desc": "Smart makes (2 PTS)", "team_abbrev": "BOS", "score": "6-0"},
        {"period": 1, "game_clock_sec": 650, "event_desc": "Harris makes (2 PTS)", "team_abbrev": "PHI", "score": "6-2"},
    ]
    (tmp_path / "pbp_0000000001_p1.json").write_text(json.dumps(events), encoding="utf-8")
    rows = vrw2.game_samples("0000000001")
    assert len(rows) == 1  # the CELTICS timeout at t=20 has a 20s before-window (<60s floor) -- dropped
    assert rows[0]["team"] == "PHI"
    assert rows[0]["ppm_before"] == 2 / (180 / 60.0)
    assert rows[0]["ppm_after"] == 2 / (180 / 60.0)


def test_rest_diff_frame_pairs_home_away_within_game():
    tg = pd.DataFrame([
        {"game_id": "g1", "team": "BOS", "date": pd.Timestamp("2026-01-01"), "is_home": 1, "rest_days": 2.0, "margin": 5.0},
        {"game_id": "g1", "team": "PHI", "date": pd.Timestamp("2026-01-01"), "is_home": 0, "rest_days": 0.0, "margin": -5.0},
        {"game_id": "g2", "team": "LAL", "date": pd.Timestamp("2026-01-02"), "is_home": 1, "rest_days": None, "margin": 3.0},
        {"game_id": "g2", "team": "GSW", "date": pd.Timestamp("2026-01-02"), "is_home": 0, "rest_days": 1.0, "margin": -3.0},
    ])
    m = vrw2._rest_diff_frame(tg)
    assert len(m) == 1  # g2 dropped: home rest_days is null
    assert m.iloc[0]["game_id"] == "g1"
    assert m.iloc[0]["rest_diff"] == 2.0


def test_rest_margin_r_below_floor_is_not_testable():
    m = pd.DataFrame({"rest_diff": [1.0] * 5, "margin": [2.0] * 5})
    r = vrw2._rest_margin_r(m, "h1")
    assert r["verdict"] == "NOT_TESTABLE"


def test_combine_halves_needs_both_confirmed_same_sign():
    confirmed_pos = {"hypothesis": "x__h1", "n": 30, "effect": 0.5, "p": 0.001, "verdict": "CONFIRMED_LOCAL"}
    confirmed_neg = {"hypothesis": "x__h2", "n": 30, "effect": -0.5, "p": 0.001, "verdict": "CONFIRMED_LOCAL"}
    out = vrw2._combine_halves([confirmed_pos, confirmed_neg], "x")
    assert out["verdict"] == "NULL_LOCAL"  # opposite signs -- not a real replication

    out2 = vrw2._combine_halves([confirmed_pos, dict(confirmed_pos, hypothesis="x__h2")], "x")
    assert out2["verdict"] == "CONFIRMED_LOCAL"


def test_run_writes_edge_free_rows_even_with_no_local_pbp(tmp_path, monkeypatch):
    ledger = tmp_path / "validation_ledger.jsonl"
    monkeypatch.setattr(vrw2, "LEDGER_PATH", ledger)
    monkeypatch.setattr(vrw2, "PBP_DIR", tmp_path)  # empty dir -> no p1 files on disk
    empty_box = pd.DataFrame(columns=["game_id", "date", "team", "is_home"])
    monkeypatch.setattr(vrw2, "load_player_boxscores", lambda: empty_box)
    empty_tg = pd.DataFrame(columns=["game_id", "date", "team", "is_home", "rest_days", "margin"])
    monkeypatch.setattr(vrw2, "team_game_frame", lambda box: empty_tg)

    rows = vrw2.run()
    assert len(rows) >= 2
    assert all(r["edge_claimed"] is False and r["sport"] == "basketball_nba" for r in rows)
    on_disk = [l for l in ledger.read_text(encoding="ascii").splitlines() if l.strip()]
    assert len(on_disk) == len(rows)
