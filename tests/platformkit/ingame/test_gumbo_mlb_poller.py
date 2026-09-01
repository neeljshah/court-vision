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


# --- live-cadence window (latency-audit fix, 2026-07-07) ---

_PRE_CHANGE_KEYS = {  # exact row keys BEFORE this change, for the fixture payload
    "game_pk", "ts", "inning", "half", "outs", "base_state", "base_label",
    "on_first", "on_second", "on_third", "balls", "strikes",
    "score_away", "score_home", "batter_id", "pitcher_id"}


def test_row_schema_unchanged_plus_additive_captured_at(tmp_path):
    def fetch(url):
        if "schedule" in url:
            return _schedule_payload(game_pk=111)
        return _bootstrap_payload(game_pk=111)

    M.run_once(date_str="2026-07-04", out_dir=tmp_path / "g",
               state_file=tmp_path / "s.json", fetch_fn=fetch, sleep_fn=lambda s: None)
    row = json.loads((tmp_path / "g" / "111.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert set(row) == _PRE_CHANGE_KEYS | {"captured_at"}, "schema must stay byte-compatible + one additive key"
    assert row["ts"] == "20260704_025709", "ts stays MLB's own metaData.timeStamp"
    assert row["captured_at"].endswith("Z") and "T" in row["captured_at"]


def test_live_cadence_env_default_and_floor(monkeypatch):
    monkeypatch.delenv("CV_GUMBO_LIVE_SEC", raising=False)
    assert M.live_cadence_sec() == 10.0
    monkeypatch.setenv("CV_GUMBO_LIVE_SEC", "2")
    assert M.live_cadence_sec() == 5.0, "never hammer below the 5s politeness floor"
    monkeypatch.setenv("CV_GUMBO_LIVE_SEC", "15")
    assert M.live_cadence_sec() == 15.0
    monkeypatch.setenv("CV_GUMBO_LIVE_SEC", "garbage")
    assert M.live_cadence_sec() == 10.0


class _FakeClock:
    def __init__(self):
        self.t = 0.0
        self.slept = []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s
        self.slept.append(s)


def _clock():
    return _FakeClock()


def test_run_live_window_fast_polls_while_live(tmp_path):
    passes = {"n": 0}

    def fetch(url):
        if "schedule" in url:
            passes["n"] += 1
            return _schedule_payload(game_pk=111)
        return _bootstrap_payload(game_pk=111)

    c = _clock()
    rep = M.run_live_window(30.0, date_str="2026-07-04", out_dir=tmp_path / "g",
                            state_file=tmp_path / "s.json", fetch_fn=fetch,
                            sleep_fn=c.sleep, clock=c, cadence_sec=10.0)
    assert rep["passes"] == 2 and rep["rows_written"] == 2
    assert c.slept == [10.0, 10.0, 10.0], "waits one cadence first, then per-pass, then remainder"
    assert passes["n"] == 2, "one schedule check per fast pass"


def test_run_live_window_goes_idle_when_no_live_games(tmp_path):
    calls = {"n": 0}

    def fetch(url):
        calls["n"] += 1
        return {"dates": []}   # nothing live

    c = _clock()
    rep = M.run_live_window(30.0, date_str="2026-07-04", out_dir=tmp_path / "g",
                            state_file=tmp_path / "s.json", fetch_fn=fetch,
                            sleep_fn=c.sleep, clock=c, cadence_sec=10.0)
    assert rep["passes"] == 1 and rep["rows_written"] == 0
    assert calls["n"] == 1, "no fast polling without a live game (idle cadence unchanged)"
    assert c.t == 30.0, "remaining window is plain-slept away, never returned early"


def test_run_live_window_backs_off_exponentially_on_error_passes(tmp_path):
    def fetch(url):
        if "schedule" in url:
            return _schedule_payload(game_pk=111)
        return None   # every game fetch fails (HTTP error path degrades to None)

    c = _clock()
    rep = M.run_live_window(100.0, date_str="2026-07-04", out_dir=tmp_path / "g",
                            state_file=tmp_path / "s.json", fetch_fn=fetch,
                            sleep_fn=c.sleep, clock=c, cadence_sec=10.0)
    assert rep["rows_written"] == 0
    assert c.slept[:3] == [10.0, 20.0, 40.0], "exponential backoff on all-error passes"
    assert max(c.slept) <= 60.0, "backoff capped"


def test_run_live_window_diffpatch_then_fallback_to_full_feed(tmp_path):
    """Steady state uses diffPatch; a broken patch falls back to the full feed -- proven
    inside the fast window (not just in poll_one_game isolation)."""
    urls = []
    bad_patch = [{"metaData": {"logicalEvents": []},
                  "diff": [{"op": "replace", "path": "/liveData/linescore/outs/99", "value": 1}]}]

    def fetch(url):
        urls.append(url)
        if "schedule" in url:
            return _schedule_payload(game_pk=111)
        if "diffPatch" in url:
            return bad_patch
        return _bootstrap_payload(game_pk=111, outs=2, ts="20260704_030000")

    state_file = tmp_path / "s.json"
    c = _clock()
    rep = M.run_live_window(21.0, date_str="2026-07-04", out_dir=tmp_path / "g",
                            state_file=state_file, fetch_fn=fetch,
                            sleep_fn=c.sleep, clock=c, cadence_sec=10.0)
    assert rep["passes"] == 2
    diffpatch_calls = [u for u in urls if "diffPatch" in u]
    full_feed_calls = [u for u in urls if "feed/live" in u and "diffPatch" not in u]
    assert diffpatch_calls, "second pass must try diffPatch (prior ts cached)"
    assert len(full_feed_calls) >= 2, "bootstrap + fallback re-fetch on patch failure"
    rows = (tmp_path / "g" / "111.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 2 and json.loads(rows[1])["outs"] == 2, "fallback row still written"


def test_default_date_is_baseball_date_not_utc(monkeypatch):
    """Past 00:00 UTC (evening US games still live), the default schedule date
    must stay on the US slate date (UTC-10h roll), not roll to tomorrow-UTC --
    the today-UTC default made capture go blind every evening at ~7pm CT."""
    from scripts.platformkit.ingame import gumbo_mlb_poller as gp
    seen = {}
    def fake_fetch(url):
        seen["url"] = url
        return {"dates": []}
    gp.list_live_game_pks(date_str=None, fetch_fn=fake_fetch)
    from datetime import datetime, timedelta, timezone
    expect = (datetime.now(timezone.utc) - timedelta(hours=10)).strftime("%Y-%m-%d")
    assert expect in seen["url"]


# ---------------------------------------------------------------------------
# S1e-CADENCE (2026-09-01): deadline pacing. The pre-fix loop slept a FULL cadence
# and THEN ran the pass, so the per-game period was cadence + pass_duration (the
# measured p50 15s against a 10s cadence). These prove the period is now
# max(cadence, pass_duration) with no pile-up and no accumulated drift.
# ---------------------------------------------------------------------------

def _costly_fetch(clock, cost, n_games=3):
    """fetch_fn that charges `cost` seconds of wall time to the fake clock per call."""
    def fetch(url):
        clock.t += cost
        if "schedule" in url:
            payload = _schedule_payload(game_pk=111)
            for extra in range(1, n_games):
                g = json.loads(json.dumps(payload["dates"][0]["games"][0]))
                g["gamePk"] = 111 + extra
                payload["dates"][0]["games"].append(g)
            return payload
        game_pk = int(url.split("/game/")[1].split("/")[0])
        return _bootstrap_payload(game_pk=game_pk)
    return fetch


def test_run_live_window_holds_target_cadence_when_fetch_is_faster(tmp_path):
    c = _clock()
    rep = M.run_live_window(60.0, date_str="2026-07-04", out_dir=tmp_path / "g",
                            state_file=tmp_path / "s.json",
                            fetch_fn=_costly_fetch(c, 0.4), sleep_fn=c.sleep, clock=c,
                            cadence_sec=5.0)
    # pass costs 0.4 (schedule) + 3*0.4 (games) + 2*0.25 (pace) = 2.1s < 5s cadence
    assert rep["passes"] >= 8
    assert abs(rep["achieved_cadence_sec"] - 5.0) < 1e-6, "achieved cadence == target"
    assert abs(rep["pass_latency_sec"] - 2.1) < 1e-6, "wall latency recorded per tick"
    # pre-fix this would have been 5.0 + 2.1 = 7.1s per period
    assert rep["achieved_cadence_sec"] < 5.0 + rep["pass_latency_sec"]


def test_run_live_window_degrades_without_pileup_when_fetch_exceeds_cadence(tmp_path):
    c = _clock()
    rep = M.run_live_window(120.0, date_str="2026-07-04", out_dir=tmp_path / "g",
                            state_file=tmp_path / "s.json",
                            fetch_fn=_costly_fetch(c, 3.0), sleep_fn=c.sleep, clock=c,
                            cadence_sec=5.0)
    # pass costs 3 + 3*3 + 0.5 = 12.5s, well over the 5s target
    assert rep["pass_latency_sec"] > 5.0
    assert abs(rep["achieved_cadence_sec"] - rep["pass_latency_sec"]) < 1e-6, \
        "period degrades to the pass duration, not pass + cadence (no pile-up)"
    assert c.slept[1:] == [] or max(c.slept[1:]) <= 5.0, "no queued-up sleeps"
    assert rep["passes"] * rep["achieved_cadence_sec"] <= 120.0 + rep["pass_latency_sec"], \
        "no drift debt: the window is never overrun by accumulated deadlines"


def test_run_once_pace_defaults_to_quarter_second_and_env_recovers_prior_behavior(monkeypatch):
    monkeypatch.delenv("CV_GUMBO_PACE_SEC", raising=False)
    assert M.live_pace_sec() == 0.25
    monkeypatch.setenv("CV_GUMBO_PACE_SEC", "1.0")
    assert M.live_pace_sec() == 1.0, "prior 1.0s behavior recoverable without a code edit"
    monkeypatch.setenv("CV_GUMBO_PACE_SEC", "not-a-number")
    assert M.live_pace_sec() == 0.25, "garbage env degrades to the default, never raises"


def test_run_once_uses_env_pace_between_games(tmp_path, monkeypatch):
    monkeypatch.setenv("CV_GUMBO_PACE_SEC", "0.25")
    c = _clock()
    rep = M.run_once(date_str="2026-07-04", out_dir=tmp_path / "g",
                     state_file=tmp_path / "s.json",
                     fetch_fn=_costly_fetch(c, 0.0), sleep_fn=c.sleep)
    assert rep["n_live_games"] == 3 and rep["n_rows_written"] == 3
    assert c.slept == [0.25, 0.25], "one pace sleep between each pair of games"
    assert M.run_once(date_str="2026-07-04", out_dir=tmp_path / "g2",
                      state_file=tmp_path / "s2.json", fetch_fn=_costly_fetch(c, 0.0),
                      sleep_fn=_FakeClock().sleep, pace_sec=1.0)["n_rows_written"] == 3
