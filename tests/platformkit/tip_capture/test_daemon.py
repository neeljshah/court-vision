"""Per-file test for tip_capture (schedule/capture/store/daemon). Offline --
every network-touching fetcher is monkeypatched/injected; no real HTTP, no
real git-repo dependency beyond a local subprocess call.

Run ONLY this file:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/tip_capture/test_daemon.py -q
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from scripts.platformkit.tip_capture import capture, daemon, schedule, store  # noqa: E402

_NOW = datetime(2026, 7, 18, 20, 0, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# Pass-scheduling math (pure)
# --------------------------------------------------------------------------- #

def test_due_passes_hits_each_window():
    assert schedule.due_passes(_NOW + timedelta(minutes=60), _NOW) == ["T60"]
    assert schedule.due_passes(_NOW + timedelta(minutes=30), _NOW) == ["T30"]
    assert schedule.due_passes(_NOW + timedelta(minutes=5), _NOW) == ["T5"]


def test_due_passes_respects_tolerance_edges():
    # T60 window is [55, 65] minutes-until-tip
    assert "T60" in schedule.due_passes(_NOW + timedelta(minutes=64), _NOW)
    assert "T60" not in schedule.due_passes(_NOW + timedelta(minutes=66), _NOW)


def test_due_passes_nothing_between_windows_or_already_captured():
    assert schedule.due_passes(_NOW + timedelta(minutes=45), _NOW) == []
    assert schedule.due_passes(_NOW + timedelta(minutes=60), _NOW, captured={"T60"}) == []


def test_next_wake_seconds_earliest_bounded():
    tip = _NOW + timedelta(minutes=70)  # T60 due in 10 min = 600s
    assert abs(schedule.next_wake_seconds([(tip, set())], _NOW) - 600.0) < 1e-6
    far = _NOW + timedelta(days=30)
    assert schedule.next_wake_seconds([(far, set())], _NOW) == schedule.MAX_SLEEP_SEC
    assert schedule.next_wake_seconds([], _NOW) == schedule.MAX_SLEEP_SEC


# --------------------------------------------------------------------------- #
# Store: append-only schema + idempotency
# --------------------------------------------------------------------------- #

def _row(pass_name: str) -> dict:
    return {"sport": "nba", "game_id": "g1", "home": "BOS", "away": "LAL",
            "tip_time": "2026-07-18T23:00:00+00:00", "capture_pass": pass_name,
            "capture_ts": _NOW.isoformat(), "source": "tip_capture",
            "model_sha": "deadbeef", "payload": {"injuries": {}, "winprob": {}}}


def test_append_row_writes_expected_schema(tmp_path):
    path = store.append_row(_row("T60"), out_dir=tmp_path)
    assert path.is_file()
    parsed = json.loads(path.read_text(encoding="utf-8").strip())
    assert parsed == _row("T60")
    assert set(parsed) == {"capture_ts", "sport", "game_id", "home", "away",
                          "tip_time", "capture_pass", "source", "model_sha", "payload"}


def test_captured_passes_for_accumulates_and_is_idempotent(tmp_path):
    store.append_row(_row("T60"), out_dir=tmp_path)
    assert store.captured_passes_for("g1", "nba", _row("T60")["tip_time"],
                                     out_dir=tmp_path) == {"T60"}
    store.append_row(_row("T30"), out_dir=tmp_path)
    assert store.captured_passes_for("g1", "nba", _row("T60")["tip_time"],
                                     out_dir=tmp_path) == {"T60", "T30"}


def test_captured_passes_for_tolerates_torn_trailing_line(tmp_path):
    path = store.store_path("nba", _row("T60")["tip_time"], out_dir=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_row("T60")) + "\n{\"sport\": \"nba\", \"game_i", encoding="utf-8")
    assert store.captured_passes_for("g1", "nba", _row("T60")["tip_time"],
                                     out_dir=tmp_path) == {"T60"}


# --------------------------------------------------------------------------- #
# Singleton
# --------------------------------------------------------------------------- #

def test_acquire_singleton_second_call_behavior(tmp_path):
    lock_path = tmp_path / "tip_capture.lock"
    assert store.acquire_singleton(lock_path) is True
    second = store.acquire_singleton(lock_path)
    try:
        import fcntl  # noqa: F401
        assert second is False  # POSIX: same process, competing fds -> blocked
    except ImportError:
        assert second is True  # Windows dev box: documented no-op guard


# --------------------------------------------------------------------------- #
# Governor caller registration (no real Kalshi network call)
# --------------------------------------------------------------------------- #

def test_capture_market_registers_tip_capture_governor_caller(monkeypatch):
    recorded = {}

    class FakeKalshi:
        def __init__(self, governor_caller=None):
            recorded["caller"] = governor_caller

        def fetch(self, sport):
            return []

    monkeypatch.setattr(capture, "KalshiProvider", FakeKalshi)
    result = capture.capture_market("nba", polymarket_fn=lambda s: [])
    assert recorded["caller"] == capture.GOVERNOR_CALLER == "tip_capture"
    assert result["kalshi"]["status"] == "ok"
    assert result["polymarket"]["status"] == "ok"


# --------------------------------------------------------------------------- #
# build_row: team-code resolution + payload composition
# --------------------------------------------------------------------------- #

def test_build_row_resolves_team_names_to_codes():
    game = {"sport": "nba", "game_id": "401", "home": "Boston Celtics",
            "away": "Los Angeles Lakers", "tip_time": "2026-07-18T23:00:00+00:00"}
    seen = {}

    def fake_dispatch(sport, home, away):
        seen["home"], seen["away"] = home, away
        return {"status": "ok", "p_home_win": 0.55}

    deps = {"injuries": lambda s: [{"player_name": "X"}],
            "winprob": fake_dispatch, "kalshi": lambda s: [], "polymarket": lambda s: []}
    row = capture.build_row(game, "T60", now=_NOW, deps=deps)
    assert seen == {"home": "BOS", "away": "LAL"}
    assert row["payload"]["winprob"]["p_home_win"] == 0.55
    assert row["payload"]["injuries"]["rows"] == [{"player_name": "X"}]
    assert row["source"] == "tip_capture" and row["capture_pass"] == "T60"
    assert row["model_sha"]  # non-empty


# --------------------------------------------------------------------------- #
# tick(): end-to-end wiring + idempotent re-tick
# --------------------------------------------------------------------------- #

def test_tick_captures_due_game_and_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.setattr(daemon, "beat", lambda *_a, **_k: None)
    tip = _NOW + timedelta(minutes=60)
    game = {"sport": "nba", "game_id": "g1", "home": "BOS", "away": "LAL",
            "tip_time": tip.isoformat()}

    def fake_schedule(sport):
        return [game] if sport == "nba" else []

    deps = {"injuries": lambda s: [], "winprob": lambda s, h, a: {"status": "ok"},
            "kalshi": lambda s: [], "polymarket": lambda s: []}
    summary = daemon.tick(sports=("nba", "wnba"), now=_NOW, out_dir=tmp_path,
                          deps=deps, schedule_fn=fake_schedule)
    assert summary["sports"]["nba"] == {"n_games": 1, "n_captured": 1}
    assert summary["sports"]["wnba"] == {"n_games": 0, "n_captured": 0}

    summary2 = daemon.tick(sports=("nba",), now=_NOW, out_dir=tmp_path,
                           deps=deps, schedule_fn=fake_schedule)
    assert summary2["sports"]["nba"]["n_captured"] == 0  # already captured this pass


# --------------------------------------------------------------------------- #
# --once CLI mode
# --------------------------------------------------------------------------- #

def test_once_mode_calls_tick_exactly_once(monkeypatch, capsys):
    calls = []

    def fake_tick(**kwargs):
        calls.append(kwargs)
        return {"as_of": "x", "sports": {}, "next_wake_sec": 1.0}

    monkeypatch.setattr(daemon, "tick", fake_tick)
    monkeypatch.setattr(sys, "argv", ["daemon.py", "--once", "--no-lock", "--sports", "nba"])
    rc = daemon._main()
    assert rc == 0
    assert len(calls) == 1
    out = json.loads(capsys.readouterr().out.strip())
    assert out["as_of"] == "x"
