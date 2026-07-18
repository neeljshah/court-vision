"""Per-file test for tip_capture.ingame_capture. Offline -- every network-touching
fetcher is monkeypatched/injected; no real HTTP.

Run ONLY this file:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/tip_capture/test_ingame_capture.py -q
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from scripts.platformkit.tip_capture import ingame_capture as ic  # noqa: E402

_NOW = datetime(2026, 7, 18, 20, 0, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# _trim_play / capture_pbp_tail
# --------------------------------------------------------------------------- #

def test_trim_play_handles_dict_and_scalar_shapes():
    dict_shape = {"id": "1", "text": "Layup", "period": {"number": 2},
                  "clock": {"displayValue": "6:52"}, "homeScore": 40, "awayScore": 38,
                  "scoringPlay": True,
                  "participants": [{"athlete": {"displayName": "Player A"}}, "junk"]}
    out = ic._trim_play(dict_shape)
    assert out == {"id": "1", "text": "Layup", "period": 2, "clock": "6:52",
                   "home_score": 40, "away_score": 38, "scoring_play": True,
                   "on_floor": ["Player A"]}
    scalar_shape = {"id": "2", "text": "Foul", "period": 3, "clock": 120}
    out2 = ic._trim_play(scalar_shape)
    assert out2["period"] == 3 and out2["clock"] == 120 and "on_floor" not in out2


def test_capture_pbp_tail_takes_last_five_and_fails_open():
    plays = [{"id": str(i), "text": f"p{i}"} for i in range(8)]
    out = ic.capture_pbp_tail("nba", "401", fetch_fn=lambda s, e: {"plays": plays})
    assert out["status"] == "ok"
    assert [p["id"] for p in out["events"]] == [str(i) for i in range(3, 8)]

    assert ic.capture_pbp_tail("nba", None)["status"] == "unavailable"
    assert ic.capture_pbp_tail("nba", "401", fetch_fn=lambda s, e: None)["status"] == "unavailable"

    def boom(s, e):
        raise RuntimeError("net down")
    assert ic.capture_pbp_tail("nba", "401", fetch_fn=boom)["status"] == "error"


# --------------------------------------------------------------------------- #
# _ingame_state_for: sport-specific live -> generic ingame_state
# --------------------------------------------------------------------------- #

def test_ingame_state_for_nba_uses_frac_elapsed_times_48():
    state = {"home_score": 58, "away_score": 55, "frac_elapsed": 0.5}
    out = ic._ingame_state_for("nba", state)
    assert out == {"elapsed": 24.0, "home_score": 58, "away_score": 55}


def test_ingame_state_for_wnba_uses_40_minutes():
    state = {"home_score": 40, "away_score": 38, "frac_elapsed": 0.25}
    out = ic._ingame_state_for("wnba", state)
    assert out["elapsed"] == 10.0


def test_ingame_state_for_mlb_needs_inning_and_half():
    complete = {"home_score": 2, "away_score": 1, "inning": 5, "half": "top"}
    assert ic._ingame_state_for("mlb", complete) == {
        "inning": 5, "half": "top", "home_score": 2, "away_score": 1}
    incomplete = {"home_score": 2, "away_score": 1, "inning": 5, "half": None}
    assert ic._ingame_state_for("mlb", incomplete) is None


def test_ingame_state_for_missing_score_is_none():
    assert ic._ingame_state_for("nba", {"frac_elapsed": 0.5}) is None


# --------------------------------------------------------------------------- #
# capture_winprob_live: team-code resolution + fail-open
# --------------------------------------------------------------------------- #

def test_capture_winprob_live_resolves_codes_and_passes_ingame_state():
    seen = {}

    def fake_dispatch(sport, home, away, ingame_state):
        seen.update(sport=sport, home=home, away=away, ingame_state=ingame_state)
        return {"status": "ok", "p_home_win": 0.6}

    state = {"elapsed": 24.0, "home_score": 58, "away_score": 55}
    out = ic.capture_winprob_live("nba", "Boston Celtics", "Los Angeles Lakers", state,
                                  dispatch_fn=fake_dispatch)
    assert out["p_home_win"] == 0.6
    assert seen == {"sport": "nba", "home": "BOS", "away": "LAL", "ingame_state": state}


def test_capture_winprob_live_fails_open():
    def boom(*_a, **_k):
        raise RuntimeError("subprocess exploded")
    out = ic.capture_winprob_live("nba", "BOS", "LAL", None, dispatch_fn=boom)
    assert out == {"status": "error", "error": "RuntimeError"}


# --------------------------------------------------------------------------- #
# build_row: schema + payload composition
# --------------------------------------------------------------------------- #

def _live_state(**overrides) -> dict:
    base = {"sport": "nba", "game_id": "401", "espn_event_id": "401",
            "home": "BOS", "away": "LAL", "home_display": "Boston Celtics",
            "away_display": "Los Angeles Lakers", "home_score": 58, "away_score": 55,
            "period": 3, "clock": 411.0, "frac_elapsed": 0.6}
    base.update(overrides)
    return base


def test_build_row_schema_and_payload():
    deps = {"winprob": lambda s, h, a, ig: {"status": "ok", "p_home_win": 0.61},
            "kalshi": lambda s: [], "polymarket": lambda s: [],
            "pbp": lambda s, e: {"plays": [{"id": "1", "text": "shot"}]}}
    row = ic.build_row(_live_state(), now=_NOW, deps=deps)
    assert set(row) == {"capture_ts", "sport", "game_id", "home", "away", "period",
                        "inning", "clock", "score_home", "score_away", "source",
                        "model_sha", "payload"}
    assert row["sport"] == "nba" and row["game_id"] == "401"
    assert row["home"] == "Boston Celtics" and row["away"] == "Los Angeles Lakers"
    assert row["period"] == 3 and row["inning"] is None and row["clock"] == 411.0
    assert row["score_home"] == 58 and row["score_away"] == 55
    assert row["source"] == "ingame_capture" and row["model_sha"]
    assert row["payload"]["winprob"]["p_home_win"] == 0.61
    assert row["payload"]["market"]["kalshi"]["status"] == "ok"
    assert row["payload"]["pbp_tail"]["events"][0]["text"] == "shot"


def test_build_row_mlb_uses_inning_not_period():
    state = _live_state(sport="mlb", inning=5, half="top", clock=None, period=None)
    deps = {"winprob": lambda s, h, a, ig: {"status": "ok"},
            "kalshi": lambda s: [], "polymarket": lambda s: [], "pbp": lambda s, e: None}
    row = ic.build_row(state, now=_NOW, deps=deps)
    assert row["inning"] == 5 and row["period"] is None and row["clock"] is None


# --------------------------------------------------------------------------- #
# tick(): end-to-end wiring, one row per live game, appended to ingame_<date>.jsonl
# --------------------------------------------------------------------------- #

def test_tick_writes_one_row_per_live_game(monkeypatch, tmp_path):
    monkeypatch.setattr(ic, "_beat", lambda *_a, **_k: None)
    deps = {"winprob": lambda s, h, a, ig: {"status": "ok"},
            "kalshi": lambda s: [], "polymarket": lambda s: [], "pbp": lambda s, e: None}

    def fake_live(sport):
        return [_live_state()] if sport == "nba" else []

    summary = ic.tick(sports=("nba", "wnba"), now=_NOW, out_dir=tmp_path,
                      deps=deps, live_fn=fake_live)
    assert summary["sports"]["nba"] == {"n_live": 1, "n_captured": 1}
    assert summary["sports"]["wnba"] == {"n_live": 0, "n_captured": 0}

    out_path = tmp_path / "nba" / "ingame_2026-07-18.jsonl"
    assert out_path.is_file()
    row = json.loads(out_path.read_text(encoding="utf-8").strip())
    assert row["game_id"] == "401"

    # a second tick appends a second row (no idempotency guard for live ticks)
    ic.tick(sports=("nba",), now=_NOW, out_dir=tmp_path, deps=deps, live_fn=fake_live)
    lines = out_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


def test_tick_one_bad_sport_does_not_sink_others(monkeypatch, tmp_path):
    monkeypatch.setattr(ic, "_beat", lambda *_a, **_k: None)
    deps = {"winprob": lambda s, h, a, ig: {"status": "ok"},
            "kalshi": lambda s: [], "polymarket": lambda s: [], "pbp": lambda s, e: None}

    def flaky_live(sport):
        if sport == "mlb":
            raise RuntimeError("scoreboard down")
        return [_live_state()] if sport == "nba" else []

    summary = ic.tick(sports=("nba", "mlb"), now=_NOW, out_dir=tmp_path,
                      deps=deps, live_fn=flaky_live)
    assert summary["sports"]["nba"]["n_captured"] == 1
    assert summary["sports"]["mlb"] == {"n_live": 0, "n_captured": 0}


# --------------------------------------------------------------------------- #
# --once CLI mode
# --------------------------------------------------------------------------- #

def test_once_mode_calls_tick_exactly_once(monkeypatch, capsys):
    calls = []

    def fake_tick(**kwargs):
        calls.append(kwargs)
        return {"as_of": "x", "sports": {}}

    monkeypatch.setattr(ic, "tick", fake_tick)
    monkeypatch.setattr(sys, "argv",
                        ["ingame_capture.py", "--once", "--no-lock", "--sports", "nba"])
    rc = ic._main()
    assert rc == 0
    assert len(calls) == 1
    out = json.loads(capsys.readouterr().out.strip())
    assert out["as_of"] == "x"
