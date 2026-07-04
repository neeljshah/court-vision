"""Per-file test for the STANDALONE MLB GUMBO poller (LANE 2).

OFFLINE + deterministic: fetch_fn is injected (a dict URL->response map / callable), so
there is NO network. out_dir / state_file are tmp_path.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        tests/platformkit/ingame/test_gumbo_mlb_poller.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.ingame import gumbo_mlb_poller as M


def _schedule_payload(game_pk=824417, status="In Progress"):
    return {"dates": [{"games": [{
        "gamePk": game_pk,
        "status": {"detailedState": status},
        "teams": {"away": {"team": {"name": "Chicago White Sox"}},
                  "home": {"team": {"name": "Cleveland Guardians"}}},
    }]}]}


def _bootstrap_payload(game_pk=824417, ts="20260704_025709", outs=1):
    return {
        "gamePk": game_pk,
        "metaData": {"timeStamp": ts, "logicalEvents": []},
        "gameData": {},
        "liveData": {
            "linescore": {"currentInning": 7, "inningState": "Bottom", "outs": outs,
                          "balls": 1, "strikes": 1,
                          "defense": {"first": {"id": 1, "fullName": "Fielder"}},
                          "offense": {"first": None, "second": None, "third": None},
                          "teams": {"away": {"runs": 3}, "home": {"runs": 2}}},
            "plays": {"currentPlay": {
                "matchup": {"batter": {"id": 100}, "pitcher": {"id": 200},
                            "postOnFirst": None, "postOnSecond": None, "postOnThird": None},
                "runners": [], "playEvents": []}},
            "boxscore": {"teams": {"away": {"players": {}}, "home": {"players": {}}}},
        },
    }


def test_list_live_game_pks_filters_in_progress_only():
    payload = _schedule_payload()
    payload["dates"][0]["games"].append({
        "gamePk": 999, "status": {"detailedState": "Final"},
        "teams": {"away": {"team": {"name": "A"}}, "home": {"team": {"name": "B"}}}})

    def fetch(url):
        return payload

    games = M.list_live_game_pks("2026-07-04", fetch_fn=fetch)
    assert len(games) == 1 and games[0]["game_pk"] == 824417
    assert games[0]["away"] == "Chicago White Sox"


def test_list_live_game_pks_empty_on_bad_schedule_response():
    assert M.list_live_game_pks("2026-07-04", fetch_fn=lambda url: None) == []
    assert M.list_live_game_pks("2026-07-04", fetch_fn=lambda url: {}) == []


def test_poll_one_game_bootstraps_when_no_prior_state():
    calls = []

    def fetch(url):
        calls.append(url)
        return _bootstrap_payload()

    state = {}
    tick = M.poll_one_game(824417, state, fetch_fn=fetch)
    assert tick["inning"] == 7 and tick["outs"] == 1
    assert "824417" in state and state["824417"]["ts"] == "20260704_025709"
    assert any("feed/live" in u and "diffPatch" not in u for u in calls)


def test_poll_one_game_uses_diffpatch_when_prior_state_present():
    prior_full = _bootstrap_payload(outs=0)
    state = {"824417": {"ts": "20260704_025700", "snapshot": prior_full}}

    diffpatch_doc = [{"metaData": {"logicalEvents": ["countChange"]},
                       "diff": [{"op": "replace", "path": "/liveData/linescore/outs",
                                 "value": 2},
                                {"op": "replace", "path": "/metaData/timeStamp",
                                 "value": "20260704_025720"}]}]

    def fetch(url):
        assert "diffPatch" in url
        return diffpatch_doc

    tick = M.poll_one_game(824417, state, fetch_fn=fetch)
    assert tick["outs"] == 2
    assert state["824417"]["ts"] == "20260704_025720"


def test_poll_one_game_fullupdate_response_used_directly():
    prior_full = _bootstrap_payload(outs=0)
    state = {"824417": {"ts": "20260704_025700", "snapshot": prior_full}}
    full_update_resp = _bootstrap_payload(outs=5, ts="20260704_025800")

    def fetch(url):
        return full_update_resp

    tick = M.poll_one_game(824417, state, fetch_fn=fetch)
    assert tick["outs"] == 5
    assert state["824417"]["ts"] == "20260704_025800"


def test_poll_one_game_falls_back_to_bootstrap_on_patch_failure():
    prior_full = _bootstrap_payload(outs=0)
    state = {"824417": {"ts": "20260704_025700", "snapshot": prior_full}}
    bad_patch = [{"metaData": {"logicalEvents": []},
                  "diff": [{"op": "replace", "path": "/liveData/linescore/outs/99", "value": 1}]}]
    fresh_bootstrap = _bootstrap_payload(outs=1, ts="20260704_025900")
    calls = {"n": 0}

    def fetch(url):
        calls["n"] += 1
        if "diffPatch" in url:
            return bad_patch
        return fresh_bootstrap

    tick = M.poll_one_game(824417, state, fetch_fn=fetch)
    assert tick["outs"] == 1   # recovered via the fallback re-fetch
    assert calls["n"] == 2      # one diffPatch attempt + one fallback bootstrap


def test_poll_one_game_returns_none_on_unusable_payload():
    assert M.poll_one_game(824417, {}, fetch_fn=lambda url: None) is None
    assert M.poll_one_game(824417, {}, fetch_fn=lambda url: {"nope": True}) is None


def test_run_once_writes_jsonl_row_and_state_error_isolated(tmp_path):
    out_dir = tmp_path / "gumbo_live"
    state_file = tmp_path / "state.json"
    sched = _schedule_payload(game_pk=111)
    sched["dates"][0]["games"].append({
        "gamePk": 222, "status": {"detailedState": "In Progress"},
        "teams": {"away": {"team": {"name": "X"}}, "home": {"team": {"name": "Y"}}}})

    def fetch(url):
        if "schedule" in url:
            return sched
        if "111" in url:
            return _bootstrap_payload(game_pk=111)
        if "222" in url:
            raise RuntimeError("simulated network blip for game 222")
        return None

    report = M.run_once(date_str="2026-07-04", out_dir=out_dir, state_file=state_file,
                         fetch_fn=fetch, sleep_fn=lambda s: None)

    assert report["n_live_games"] == 2
    assert report["n_rows_written"] == 1
    assert any("222" in e for e in report["errors"])
    row_file = out_dir / "111.jsonl"
    assert row_file.exists()
    row = json.loads(row_file.read_text(encoding="utf-8").strip().splitlines()[0])
    assert row["inning"] == 7
    assert state_file.exists()


def test_run_once_no_live_games_clean_zero_report(tmp_path):
    def fetch(url):
        return {"dates": []}

    report = M.run_once(date_str="2026-07-04", out_dir=tmp_path / "g",
                         state_file=tmp_path / "s.json", fetch_fn=fetch,
                         sleep_fn=lambda s: None)
    assert report["n_live_games"] == 0 and report["n_rows_written"] == 0
