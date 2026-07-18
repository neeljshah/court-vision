"""LANE F -- winprob_dispatch tests. Monkeypatches subprocess.run so no real
predict_matchup.py process is spawned; proves the envelope contract holds for
the ok / nonzero-exit / bad-json / timeout paths.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/answers/test_winprob_dispatch.py -q
"""
from __future__ import annotations

import json
import subprocess
import threading
import time

import pytest

from scripts.platformkit.answers import winprob_dispatch as D


class _Proc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


_FIXED_RESULT = {
    "sport": "mlb", "home": "NYY", "away": "BOS", "edge_claimed": False,
    "framing": "Pregame MATCHES the devigged close. No $ edge.",
    "pregame": {"p_home_win": 0.529, "expected_total": 7.477, "honest_note": "n/a"},
}


def test_ok_envelope_verbatim(monkeypatch):
    monkeypatch.setattr(subprocess, "run",
        lambda *a, **k: _Proc(0, json.dumps(_FIXED_RESULT), ""))
    r = D.dispatch("mlb", "NYY", "BOS")
    assert r["status"] == "ok"
    assert r["category"] == "winprob"
    assert r["source_artifact"] == "scripts/platformkit/predict_matchup.py"
    assert r["pregame"] == _FIXED_RESULT["pregame"]
    assert r["p_home_win"] == 0.529  # quoted verbatim off pregame block
    assert r["edge_claimed"] is False
    assert "as_of" in r


def test_ingame_block_passed_through(monkeypatch):
    with_ingame = {**_FIXED_RESULT, "ingame": {"p_home_win": 0.61, "proj_total": 8.1}}
    monkeypatch.setattr(subprocess, "run",
        lambda *a, **k: _Proc(0, json.dumps(with_ingame), ""))
    r = D.dispatch("mlb", "NYY", "BOS", ingame_state={"inning": 5, "half": "top",
                                                       "home_score": 3, "away_score": 2})
    assert r["ingame"] == with_ingame["ingame"]
    assert r["p_home_win"] == 0.61  # ingame takes priority over pregame


def test_nonzero_exit_is_no_data(monkeypatch):
    monkeypatch.setattr(subprocess, "run",
        lambda *a, **k: _Proc(2, "", "predict_matchup: error: argument --sport: invalid choice"))
    r = D.dispatch("bogussport", "ZZZ", "QQQ")
    assert r["status"] == "no_data"
    assert "invalid choice" in r["note"]


def test_unparseable_stdout_is_no_data(monkeypatch):
    monkeypatch.setattr(subprocess, "run",
        lambda *a, **k: _Proc(0, "mlb: corpus unavailable on this clone; see docs.", ""))
    r = D.dispatch("mlb", "NYY", "BOS")
    assert r["status"] == "no_data"
    assert "corpus unavailable" in r["note"]


def test_timeout_is_no_data(monkeypatch):
    def _raise(*a, **k):
        raise subprocess.TimeoutExpired(cmd="predict_matchup", timeout=60)
    monkeypatch.setattr(subprocess, "run", _raise)
    r = D.dispatch("mlb", "NYY", "BOS")
    assert r["status"] == "no_data"
    assert "timed out" in r["note"]


def test_concurrent_dispatch_is_serialized(monkeypatch):
    # golive_hardening_backlog #10: no cap on concurrent subprocess launches
    # (total-outage risk -- box_ram_crashes_2026_07_16). Two threads calling
    # dispatch() at once must never run subprocess.run simultaneously.
    concurrent = 0
    max_concurrent = 0
    lock = threading.Lock()

    def _slow_run(*a, **k):
        nonlocal concurrent, max_concurrent
        with lock:
            concurrent += 1
            max_concurrent = max(max_concurrent, concurrent)
        time.sleep(0.05)
        with lock:
            concurrent -= 1
        return _Proc(0, json.dumps(_FIXED_RESULT), "")

    monkeypatch.setattr(subprocess, "run", _slow_run)
    threads = [threading.Thread(target=D.dispatch, args=("mlb", "NYY", "BOS"))
               for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert max_concurrent == 1
