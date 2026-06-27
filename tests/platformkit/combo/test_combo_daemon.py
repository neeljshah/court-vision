"""tests.platformkit.combo.test_combo_daemon -- bounded loop is inert + checkpoint-resumable.

A bounded run_forever (fake clock/sleep, max_cycles) with the sentinel ABSENT yields
NO_CANDIDATE every cycle and ships nothing. Per-file test only. ASCII; stdlib deps.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[3]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from scripts.platformkit.combo import combo_daemon as DAE  # noqa: E402
from scripts.platformkit.combo import combo_runner as RUN  # noqa: E402
from scripts.platformkit.improve import pipeline_flag as PF  # noqa: E402


def _settled_fn(name, since="", seen_ids=None, **kw):
    games = []
    for i in range(12):
        det = {"run_diff": float(i), "pace": float(1 + (i % 3))}
        games.append({"sport": name, "game_id": "G%02d" % i, "outcome": 1.0,
                      "states": [{"p0": 0.55, "outcome": 1.0, "detail": det},
                                 {"p0": 0.40, "outcome": 0.0, "detail": det}]})
    return games


def test_bounded_forever_is_inert_when_sentinel_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(PF, "SENTINEL_PATH", tmp_path / "ABSENT")
    ticks = {"t": 0.0}

    def _clock():
        ticks["t"] += 1.0
        return ticks["t"]

    results = DAE.run_forever(
        names=("nba",), interval_sec=0.0, max_cycles=2,
        clock=_clock, sleep=lambda s: None,
        settled_games_fn=_settled_fn,
        ckpt_path=str(tmp_path / "ckpt.json"),
        state_path=str(tmp_path / "bandit.json"),
        proposals_path=str(tmp_path / "prop.jsonl"),
        reject_path=str(tmp_path / "rej.jsonl"),
        status_path=str(tmp_path / "stat.jsonl"))
    assert len(results) == 2
    assert all(r.decision == RUN.NO_CANDIDATE for r in results)
    assert all(r.n_proposed == 0 for r in results)
    # No proposals file written with content (nothing ever shipped).
    pp = tmp_path / "prop.jsonl"
    assert (not pp.exists()) or pp.read_text().strip() == ""


def test_should_stop_halts_loop(monkeypatch, tmp_path):
    monkeypatch.setattr(PF, "SENTINEL_PATH", tmp_path / "ABSENT")
    results = DAE.run_forever(
        names=("nba",), interval_sec=0.0, max_cycles=10,
        clock=lambda: 1.0, sleep=lambda s: None,
        should_stop=lambda: True,
        settled_games_fn=_settled_fn,
        ckpt_path=str(tmp_path / "ckpt.json"))
    assert results == []  # stopped before the first cycle.
