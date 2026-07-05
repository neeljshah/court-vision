"""Per-file tests for domains.basketball_wnba.atlas_extract_context.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_atlas_extract_context.py -q
"""
from __future__ import annotations

import json
from datetime import datetime

import pandas as pd

import domains.basketball_wnba.atlas_extract_common as common
from domains.basketball_wnba.atlas_extract_context import (
    CREW_CLAIM_FLOOR, build_arena_attendance_context, build_referee_crew_foul_rate,
    build_schedule_density, run_extract_context,
)

HOME_ID, AWAY_ID = 1611661313, 1611661325


def _officials():
    return [
        {"personId": 111, "name": "A. One"},
        {"personId": 222, "name": "B. Two"},
        {"personId": 333, "name": "C. Three"},
    ]


def _box_game(attendance=10000, sellout=0, game_et="2026-04-25T15:00:00-04:00"):
    return {
        "homeTeam": {"teamId": HOME_ID, "teamTricode": "NYL"},
        "awayTeam": {"teamId": AWAY_ID, "teamTricode": "IND"},
        "officials": _officials(),
        "attendance": attendance,
        "sellout": sellout,
        "arena": {"arenaName": "Barclays Center", "arenaCity": "Brooklyn", "arenaState": "NY"},
        "gameEt": game_et,
    }


def _foul_action(official_id, sub_type="personal"):
    return {"actionType": "foul", "officialId": official_id, "subType": sub_type}


def _write_game(tmp_path, gid, box_game, foul_events=None):
    d = tmp_path / gid
    d.mkdir()
    (d / "boxscore.json").write_text(json.dumps({"game": box_game}), encoding="utf-8")
    actions = [_foul_action(o["personId"]) for o in box_game.get("officials", [])] \
        if foul_events is None else foul_events
    (d / "playbyplay.json").write_text(
        json.dumps({"game": {"actions": actions}}), encoding="utf-8")


# ---------------------------------------------------------------------------
# build_referee_crew_foul_rate
# ---------------------------------------------------------------------------

def test_referee_crew_foul_rate_basic(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "BACKFILL_DIR", tmp_path)
    # official 111 calls 2 fouls in g1, 1 in g2 -> n_games=2, total=3
    _write_game(tmp_path, "g1", _box_game(),
                foul_events=[_foul_action(111), _foul_action(111), _foul_action(222)])
    _write_game(tmp_path, "g2", _box_game(),
                foul_events=[_foul_action(111), _foul_action(333)])
    df = build_referee_crew_foul_rate()
    row = df[df["official_id"] == "111"].iloc[0]
    assert row["n_games"] == 2
    assert row["total_fouls_called"] == 3
    assert row["fouls_per_game"] == 1.5
    assert row["official_name"] == "A. One"
    assert bool(row["claim_eligible"]) is False  # n_games=2 < floor(10)


def test_referee_crew_foul_rate_claim_eligible_floor(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "BACKFILL_DIR", tmp_path)
    for i in range(CREW_CLAIM_FLOOR):
        _write_game(tmp_path, f"g{i}", _box_game(), foul_events=[_foul_action(111)])
    df = build_referee_crew_foul_rate()
    row = df[df["official_id"] == "111"].iloc[0]
    assert row["n_games"] == CREW_CLAIM_FLOOR
    assert bool(row["claim_eligible"]) is True


def test_referee_crew_foul_rate_ignores_non_foul_actions(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "BACKFILL_DIR", tmp_path)
    _write_game(tmp_path, "g1", _box_game(),
                foul_events=[{"actionType": "2pt", "officialId": 111}])
    df = build_referee_crew_foul_rate()
    assert df.empty


def test_referee_crew_foul_rate_empty_corpus(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "BACKFILL_DIR", tmp_path)
    df = build_referee_crew_foul_rate()
    assert df.empty


# ---------------------------------------------------------------------------
# build_arena_attendance_context
# ---------------------------------------------------------------------------

def test_arena_attendance_context_game_grain(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "BACKFILL_DIR", tmp_path)
    _write_game(tmp_path, "g1", _box_game(attendance=14662, sellout=1))
    _write_game(tmp_path, "g2", _box_game(attendance=9000, sellout=0))
    df = build_arena_attendance_context()
    assert len(df) == 2  # ONE row per game, not team-aggregated
    row = df[df["game_id"] == "g1"].iloc[0]
    assert row["attendance"] == 14662
    assert row["sellout"] == 1
    assert row["arena_name"] == "Barclays Center"
    assert row["home_team_tricode"] == "NYL"
    assert row["away_team_tricode"] == "IND"


def test_arena_attendance_context_empty_corpus(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "BACKFILL_DIR", tmp_path)
    df = build_arena_attendance_context()
    assert df.empty


# ---------------------------------------------------------------------------
# build_schedule_density -- pure date arithmetic
# ---------------------------------------------------------------------------

def _scoreboard_row(event_id, date_str, home, away, season="2026"):
    return {"event_id": event_id, "date": datetime.strptime(date_str, "%Y-%m-%d"),
            "season": season, "home_team": home, "away_team": away}


def test_schedule_density_counts_trailing_windows():
    rows = [
        _scoreboard_row("e1", "2026-04-01", "Team A", "Team B"),
        _scoreboard_row("e2", "2026-04-05", "Team A", "Team C"),   # 4 days after e1
        _scoreboard_row("e3", "2026-04-10", "Team A", "Team B"),   # 9d after e1, 5d after e2
        _scoreboard_row("e4", "2026-04-20", "Team A", "Team C"),   # 19d/15d/10d after e1/e2/e3
    ]
    sb = pd.DataFrame(rows)
    df = build_schedule_density(sb)
    team_a = df[df["team"] == "Team A"].sort_values("date").reset_index(drop=True)
    assert len(team_a) == 4
    # e1 (2026-04-01): no prior games
    assert team_a.iloc[0]["games_last_7d"] == 0
    assert team_a.iloc[0]["games_last_14d"] == 0
    # e2 (2026-04-05): e1 is 4 days prior -> within both windows
    assert team_a.iloc[1]["games_last_7d"] == 1
    assert team_a.iloc[1]["games_last_14d"] == 1
    # e3 (2026-04-10): e2 is 5d prior (in-window), e1 is 9d prior (only 14d window)
    assert team_a.iloc[2]["games_last_7d"] == 1
    assert team_a.iloc[2]["games_last_14d"] == 2
    # e4 (2026-04-20): e3 is 10d prior (14d only), e2/e1 too far (19/15d)
    assert team_a.iloc[3]["games_last_7d"] == 0
    assert team_a.iloc[3]["games_last_14d"] == 1


def test_schedule_density_home_and_away_both_counted():
    rows = [
        _scoreboard_row("e1", "2026-04-01", "Team A", "Team B"),
        _scoreboard_row("e2", "2026-04-03", "Team C", "Team B"),  # Team B as AWAY
    ]
    sb = pd.DataFrame(rows)
    df = build_schedule_density(sb)
    team_b_games = df[df["team"] == "Team B"]
    assert len(team_b_games) == 2  # counted once per game regardless of home/away


def test_schedule_density_empty_scoreboard():
    df = build_schedule_density(pd.DataFrame())
    assert df.empty


def test_schedule_density_missing_file(monkeypatch, tmp_path):
    import domains.basketball_wnba.atlas_extract_context as mod
    monkeypatch.setattr(mod, "ESPN_SCOREBOARD_PATH", tmp_path / "missing.parquet")
    df = build_schedule_density()
    assert df.empty


# ---------------------------------------------------------------------------
# run_extract_context -- disk round-trip
# ---------------------------------------------------------------------------

def test_run_extract_context_writes_parquets(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "BACKFILL_DIR", tmp_path / "backfill")
    (tmp_path / "backfill").mkdir()
    _write_game(tmp_path / "backfill", "g1", _box_game())

    out_dir = tmp_path / "out"
    import domains.basketball_wnba.atlas_extract_context as mod
    monkeypatch.setattr(mod, "CONTEXT_OUT_DIR", out_dir)
    monkeypatch.setattr(mod, "ESPN_SCOREBOARD_PATH", tmp_path / "missing_scoreboard.parquet")

    summary = run_extract_context()
    assert summary["referee_crew_foul_rate"] == 3  # 3 officials
    assert summary["arena_attendance_context"] == 1
    assert summary["schedule_density"] == 0  # no scoreboard file -> empty, not written
    assert (out_dir / "referee_crew_foul_rate.parquet").exists()
    assert (out_dir / "arena_attendance_context.parquet").exists()
    assert not (out_dir / "schedule_density.parquet").exists()
