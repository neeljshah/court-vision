"""Per-file test for scripts.platformkit.ingame.kbo_relay_state_provider.

Fixtures are the ACTUAL LIVE payloads captured 2026-07-05 for game
20260705OBWO02026 (2 polls, 66s apart, mid-8th-inning) -- see
data/domains/kbo/naver_relay_live_sample_2026-07-05.json for the full raw
save with as-of fetch timestamps. No network: http_get/relay are injected.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_kbo_relay_state_provider.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.platformkit.ingame.kbo_relay_state_provider import (
    append_state_row,
    make_kbo_state_fn,
    relay_state_for_game,
)

_GID = "20260705OBWO02026"


def _poll1_fixture() -> dict:
    """REAL live payload, poll 1 of 2 (as_of 2026-07-05T07:29:05Z)."""
    return {
        "category": "kbo", "gameId": _GID, "no": 79, "inn": 8, "homeOrAway": "0",
        "currentGameState": {
            "homeScore": "1", "awayScore": "5", "homeHit": "6", "awayHit": "8",
            "homeBallFour": "1", "awayBallFour": "3", "homeError": "1", "awayError": "0",
            "pitcher": "76118", "batter": "53554",
            "strike": "0", "ball": "1", "out": "2",
            "base1": "0", "base2": "8", "base3": "0",
        },
        "inningScore": {
            "home": {"1": "0", "2": "0", "3": "1", "4": "0", "5": "0", "6": "0", "7": "0", "8": "-"},
            "away": {"1": "0", "2": "1", "3": "0", "4": "3", "5": "0", "6": "0", "7": "0", "8": "1"},
        },
    }


def _poll2_fixture() -> dict:
    """REAL live payload, poll 2 of 2 (as_of 2026-07-05T07:30:11Z, 66s after poll1).

    PROGRESSED vs poll1: awayScore 5->6, base1/base2 changed, pitcher/batter both
    rotated, ball 1->0, relay seq no 79->80 -- the exact evidence that confirmed
    live_confirmed=True this wave."""
    return {
        "category": "kbo", "gameId": _GID, "no": 80, "inn": 8, "homeOrAway": "0",
        "currentGameState": {
            "homeScore": "1", "awayScore": "6", "homeHit": "6", "awayHit": "9",
            "homeBallFour": "1", "awayBallFour": "3", "homeError": "1", "awayError": "0",
            "pitcher": "69360", "batter": "77532",
            "strike": "0", "ball": "0", "out": "2",
            "base1": "1", "base2": "0", "base3": "0",
        },
        "inningScore": {
            "home": {"1": "0", "2": "0", "3": "1", "4": "0", "5": "0", "6": "0", "7": "0", "8": "-"},
            "away": {"1": "0", "2": "1", "3": "0", "4": "3", "5": "0", "6": "0", "7": "0", "8": "2"},
        },
    }


def test_relay_state_for_game_poll1():
    row = relay_state_for_game(_GID, relay=_poll1_fixture())
    fetch_ts = row.pop("fetch_ts")  # non-deterministic wall clock; shape-checked separately
    assert row == {
        "game_id": _GID, "inning": 8, "half": "top", "outs": 2,
        "base_state": "-2-", "score_home": 1, "score_away": 5, "count": "1-0",
    }
    assert fetch_ts.endswith("Z")


def test_relay_state_for_game_poll2_progressed():
    row = relay_state_for_game(_GID, relay=_poll2_fixture())
    assert row["inning"] == 8
    assert row["half"] == "top"
    assert row["outs"] == 2
    assert row["base_state"] == "1--"
    assert row["score_away"] == 6
    assert row["count"] == "0-0"
    # The two polls' rows genuinely differ -- this IS the progression evidence.
    row1 = relay_state_for_game(_GID, relay=_poll1_fixture())
    assert row1["base_state"] != row["base_state"]
    assert row1["score_away"] != row["score_away"]


def test_half_from_home_or_away_bottom():
    relay = dict(_poll1_fixture())
    relay["homeOrAway"] = "1"
    row = relay_state_for_game(_GID, relay=relay)
    assert row["half"] == "bottom"


def test_half_from_home_or_away_unrecognized_is_none():
    relay = dict(_poll1_fixture())
    relay["homeOrAway"] = "?"
    row = relay_state_for_game(_GID, relay=relay)
    assert row["half"] is None


def test_relay_state_for_game_none_on_bad_shape():
    assert relay_state_for_game(_GID, relay={"nope": 1}) is None
    assert relay_state_for_game(_GID, relay=None,
                                http_get=lambda url, timeout=15.0: {"result": {}}) is None


def test_relay_state_for_game_never_raises_on_http_exception():
    assert relay_state_for_game(
        _GID, http_get=lambda url, timeout=15.0: (_ for _ in ()).throw(
            ConnectionError("down"))) is None


def test_relay_state_for_game_all_none_fields_treated_as_absent():
    relay = {"category": "kbo", "gameId": _GID}  # no inn/homeOrAway/currentGameState
    assert relay_state_for_game(_GID, relay=relay) is None


def test_append_state_row_writes_jsonl(tmp_path):
    row = relay_state_for_game(_GID, relay=_poll1_fixture())
    out_dir = Path(tmp_path) / "kbo_relay_state"
    ok = append_state_row(_GID, row, out_dir=out_dir)
    assert ok is True
    path = out_dir / ("%s.jsonl" % _GID)
    assert path.is_file()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    loaded = json.loads(lines[0])
    assert loaded["inning"] == 8
    assert loaded["score_away"] == 5


def test_append_state_row_appends_multiple_rows(tmp_path):
    out_dir = Path(tmp_path) / "kbo_relay_state"
    row1 = relay_state_for_game(_GID, relay=_poll1_fixture())
    row2 = relay_state_for_game(_GID, relay=_poll2_fixture())
    append_state_row(_GID, row1, out_dir=out_dir)
    append_state_row(_GID, row2, out_dir=out_dir)
    path = out_dir / ("%s.jsonl" % _GID)
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["score_away"] == 5
    assert json.loads(lines[1])["score_away"] == 6


def test_append_state_row_never_raises_on_bad_dir(monkeypatch):
    import scripts.platformkit.ingame.kbo_relay_state_provider as mod

    class _BoomPath:
        def __truediv__(self, other):
            raise OSError("disk full")

    monkeypatch.setattr(mod, "DEFAULT_STATE_DIR", _BoomPath())
    row = {"game_id": _GID, "inning": 8}
    assert append_state_row(_GID, row) is False


def test_make_kbo_state_fn_capture_true_writes_and_returns(tmp_path):
    out_dir = Path(tmp_path) / "kbo_relay_state"
    fn = make_kbo_state_fn(
        http_get=lambda url, timeout=15.0: {"result": {"textRelayData": _poll1_fixture()}},
        out_dir=out_dir, capture=True)
    row = fn(_GID)
    assert row is not None
    assert row["inning"] == 8
    path = out_dir / ("%s.jsonl" % _GID)
    assert path.is_file()
    assert len(path.read_text(encoding="utf-8").strip().splitlines()) == 1


def test_make_kbo_state_fn_capture_false_skips_disk(tmp_path):
    out_dir = Path(tmp_path) / "kbo_relay_state"
    fn = make_kbo_state_fn(
        http_get=lambda url, timeout=15.0: {"result": {"textRelayData": _poll1_fixture()}},
        out_dir=out_dir, capture=False)
    row = fn(_GID)
    assert row is not None
    assert not (out_dir / ("%s.jsonl" % _GID)).exists()


def test_make_kbo_state_fn_never_raises_on_dead_feed(tmp_path):
    fn = make_kbo_state_fn(
        http_get=lambda url, timeout=15.0: (_ for _ in ()).throw(ConnectionError("down")),
        out_dir=Path(tmp_path) / "kbo_relay_state")
    assert fn(_GID) is None
