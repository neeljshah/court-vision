"""Per-file tests for wedge_restarter (M40). Offline; pure evaluate + tmp IO.

Covers the 3-consecutive-RED emit, the GREEN-resets-streak rule, the per-daemon
cooldown rate-limit guard, protected-daemon exclusion, and the tick IO round trip
(request append + state persist + heartbeat).

Run ONLY this file:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ops_sentinel/test_wedge_restarter.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from scripts.platformkit.ops_sentinel import wedge_restarter as wr  # noqa: E402

_D = "m20_ingame_clv_verdict"


def _rows(*red_names, all_names=None):
    names = list(all_names) if all_names is not None else list(red_names)
    return [{"name": n, "status": "RED" if n in red_names else "GREEN"} for n in names]


def test_three_consecutive_red_emits_request():
    state = {}
    out = []
    for i in range(3):
        r, state = wr.evaluate(_rows(_D), state, now=float(i))
        out.append(r)
    assert out[0] == [] and out[1] == []
    assert len(out[2]) == 1
    assert out[2][0]["daemon"] == _D
    assert out[2][0]["consecutive_red"] == 3


def test_green_resets_the_streak():
    state = {}
    _, state = wr.evaluate(_rows(_D), state, now=0.0)
    _, state = wr.evaluate(_rows(_D), state, now=1.0)
    _, state = wr.evaluate(_rows(all_names=[_D]), state, now=2.0)  # a GREEN read
    assert state["consecutive_red"][_D] == 0
    r, _ = wr.evaluate(_rows(_D), state, now=3.0)
    assert r == []  # streak restarted -> only 1 RED, below threshold


def test_rate_limit_guard():
    state = {}
    for i in range(3):
        r, state = wr.evaluate(_rows(_D), state, now=float(i), cooldown_sec=1800.0)
    assert len(r) == 1  # first emit at the 3rd RED
    for i in range(3, 6):  # stays RED WITHIN the cooldown -> no second request
        r, state = wr.evaluate(_rows(_D), state, now=float(i), cooldown_sec=1800.0)
    assert r == []
    emitted = []
    for t in (2000.0, 2001.0, 2002.0):  # cooldown elapsed -> fires again
        r, state = wr.evaluate(_rows(_D), state, now=t, cooldown_sec=1800.0)
        emitted += r
    assert len(emitted) == 1


def test_protected_daemon_never_requested():
    for prot in sorted(wr.PROTECTED):
        state = {}
        for i in range(5):
            r, state = wr.evaluate(_rows(prot), state, now=float(i))
            assert r == [], prot


def test_dropped_daemon_row_does_not_persist_stale_red():
    state = {}
    _, state = wr.evaluate(_rows(_D), state, now=0.0)
    _, state = wr.evaluate(_rows(_D), state, now=1.0)
    # next scan no longer reports the daemon at all -> its streak is forgotten
    _, state = wr.evaluate([], state, now=2.0)
    assert _D not in state["consecutive_red"]


def test_tick_writes_request_persists_state_and_beats(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    req_path = tmp_path / "restart_requests.jsonl"
    rows = [{"name": _D, "status": "RED"}]
    beats = []
    monkeypatch.setattr(wr, "_beat", lambda now=None: beats.append(now))
    for i in range(3):
        wr.tick(now=float(i), load_rows_fn=lambda: rows,
                state_path=state_path, request_path=req_path)
    lines = [ln for ln in req_path.read_text(encoding="ascii").splitlines() if ln.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["daemon"] == _D
    st = json.loads(state_path.read_text(encoding="ascii"))
    assert st["consecutive_red"][_D] == 0  # reset after the emit
    assert beats == [0.0, 1.0, 2.0]
