"""Per-file test for scripts.platformkit.mlb_lineups_backfill. Run ONLY this file:

  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_mlb_lineups_backfill.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit import mlb_lineups_backfill as lb


def _boxscore(home_starters, away_starters, home_pitchers, away_pitchers):
    """Build a minimal statsapi boxscore dict shaped like the real endpoint."""
    def _players(starters, pitchers):
        out = {}
        for pid, name, order, pos in starters:
            out["ID%s" % pid] = {
                "person": {"id": pid, "fullName": name},
                "battingOrder": str(order * 100), "position": {"abbreviation": pos},
            }
        for pid, name in pitchers:
            out.setdefault("ID%s" % pid, {"person": {"id": pid, "fullName": name}})
        return out
    return {
        "teams": {
            "home": {"players": _players(home_starters, home_pitchers),
                     "pitchers": [p[0] for p in home_pitchers]},
            "away": {"players": _players(away_starters, away_pitchers),
                     "pitchers": [p[0] for p in away_pitchers]},
        }
    }


def test_starting_lineup_excludes_substitutions():
    """battingOrder '201' (a mid-game sub in slot 2) must NOT appear as a starter;
    only the clean multiples of 100 do, sorted by slot."""
    team_box = {"players": {
        "ID1": {"person": {"id": 1, "fullName": "Leadoff"}, "battingOrder": "100",
                "position": {"abbreviation": "CF"}},
        "ID2": {"person": {"id": 2, "fullName": "Two Hole"}, "battingOrder": "200",
                "position": {"abbreviation": "SS"}},
        "ID3": {"person": {"id": 3, "fullName": "Sub"}, "battingOrder": "201",
                "position": {"abbreviation": "1B"}},
    }}
    lineup = lb._starting_lineup(team_box)
    assert [p["name"] for p in lineup] == ["Leadoff", "Two Hole"]
    assert [p["order"] for p in lineup] == [1, 2]


def test_starting_pitcher_is_first_in_pitchers_list():
    team_box = {"pitchers": [10, 11], "players": {
        "ID10": {"person": {"id": 10, "fullName": "Starter"}},
        "ID11": {"person": {"id": 11, "fullName": "Reliever"}},
    }}
    assert lb._starting_pitcher(team_box) == {"id": 10, "name": "Starter"}
    assert lb._starting_pitcher({"pitchers": [], "players": {}}) is None


def test_eval_dates_covers_ts_date_and_minus_one_day(tmp_path):
    """A grade file's first tick UTC hour 02 (past midnight) must yield BOTH its own
    date and the day before -- the west-coast-game landmine."""
    grade_dir = tmp_path / "mlb"
    grade_dir.mkdir()
    (grade_dir / "1.jsonl").write_text(
        json.dumps({"ts": "2026-06-20T02:15:00Z"}) + "\n", encoding="utf-8")
    (grade_dir / "2.jsonl").write_text(
        json.dumps({"ts": "2026-06-19T18:00:00Z"}) + "\n", encoding="utf-8")
    dates = lb.eval_dates(grade_dir)
    assert dates == ["2026-06-18", "2026-06-19", "2026-06-20"]


def test_fetch_date_skips_already_cached(tmp_path):
    out_dir = tmp_path / "mlb_lineups"
    out_dir.mkdir()
    fp = out_dir / "2026-06-19.jsonl"
    fp.write_text(json.dumps({"game_pk": 1}) + "\n", encoding="ascii")

    def _fail_if_called(url):
        raise AssertionError("http should not be called for a cached date")

    res = lb.fetch_date("2026-06-19", out_dir, delay_s=0.0, http=_fail_if_called)
    assert res == {"date": "2026-06-19", "status": "CACHED", "n_games": 1}


def test_fetch_date_writes_rows_and_drops_empty_lineups(tmp_path, monkeypatch):
    out_dir = tmp_path / "mlb_lineups"
    good_box = _boxscore(
        home_starters=[(1, "Home One", 1, "CF")], away_starters=[(2, "Away One", 1, "LF")],
        home_pitchers=[(3, "Home SP")], away_pitchers=[(4, "Away SP")])
    empty_box = {"teams": {"home": {"players": {}, "pitchers": []},
                           "away": {"players": {}, "pitchers": []}}}

    def _fake_schedule(date_str, http):
        return [{"game_pk": 100, "home": "Home Team", "away": "Away Team"},
                {"game_pk": 101, "home": "H2", "away": "A2"}]
    monkeypatch.setattr(lb, "_fetch_statsapi_games", _fake_schedule)

    def _fake_http(url):
        if "100" in url:
            return good_box
        return empty_box

    res = lb.fetch_date("2026-06-19", out_dir, delay_s=0.0, http=_fake_http)
    assert res["status"] == "OK"
    assert res["n_games"] == 1  # game_pk 101's empty lineup was dropped, not written
    fp = out_dir / "2026-06-19.jsonl"
    rows = [json.loads(l) for l in fp.read_text(encoding="ascii").splitlines()]
    assert len(rows) == 1
    assert rows[0]["game_pk"] == 100
    assert rows[0]["home_lineup"][0]["name"] == "Home One"
    assert rows[0]["home_sp"] == {"id": 3, "name": "Home SP"}


def test_run_dates_respects_max_seconds_budget(tmp_path, monkeypatch):
    calls = []

    def _fake_fetch_date(date_str, out_dir, delay_s, http):
        calls.append(date_str)
        return {"date": date_str, "status": "OK", "n_games": 1}
    monkeypatch.setattr(lb, "fetch_date", _fake_fetch_date)

    import time as time_mod
    t = {"now": 0.0}
    monkeypatch.setattr(time_mod, "monotonic", lambda: t["now"])

    def _budget_check(*a, **k):
        t["now"] += 100.0  # exceed the 1s budget after the first date
        return {"date": a[0], "status": "OK", "n_games": 1}
    monkeypatch.setattr(lb, "fetch_date", _budget_check)

    res = lb.run_dates(["d1", "d2", "d3"], out_dir=tmp_path, max_seconds=1.0,
                       http=lambda u: None)
    statuses = [r["status"] for r in res["results"]]
    assert statuses[0] == "OK"
    assert "SKIPPED_BUDGET" in statuses
