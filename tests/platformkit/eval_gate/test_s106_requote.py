"""S306: direct construct coverage for the S106 archive re-quote join.

Run: python -m pytest tests/platformkit/eval_gate/test_s106_requote.py -q
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from scripts.platformkit.eval_gate import s106_requote as requote
from scripts.platformkit.eval_gate.tick_informative import _quote


_PREREG = (Path(__file__).resolve().parents[3] / "docs" / "evidence" / "harness" /
           "S306_s106_requote_test_prereg_2026-09-04.md")
_SEAL = "dc33d5e72bdf47962f26183f09071f60ebf0ee62b1151f0088208a23157f5dd0"


def _frame() -> pd.DataFrame:
    return pd.DataFrame([
        {"game": "A", "timestamp": "2026-07-05T20:00:00Z", "loss": 0.4},
        {"game": "A", "timestamp": "2026-07-05T20:01:00Z", "loss": -0.2},
        {"game": "B", "timestamp": "2026-07-05T20:02:00Z", "loss": 0.1},
    ])


def _attached() -> tuple[pd.DataFrame, dict]:
    frame = _frame()
    coverage = requote._attach(
        frame,
        {("A", "2026-07-05T20:00:00Z"): 2},
        "game",
        "timestamp",
    )
    return frame, coverage


def test_matched_tick_uses_its_real_game_sequence():
    frame, _ = _attached()
    assert frame.loc[0, "real_game_seq"] == 2
    assert frame.loc[0, "cluster"] == "A#2"


def test_unmatched_tick_remains_in_first_sequence():
    frame, _ = _attached()
    assert frame.loc[2, "real_game_seq"] == 1
    assert frame.loc[2, "cluster"] == "B#1"


def test_attach_preserves_input_row_count():
    frame, coverage = _attached()
    assert len(frame) == 3
    assert coverage == {"n_rows": 3, "n_unmatched_in_joined_store": 2}


def test_before_ci_reproduces_before_correction_and_prereg_seal():
    frame, _ = _attached()
    pair = requote._pair(frame, "game", "loss")
    expected_before = _quote(frame, "game", "loss")
    assert pair["before_game_id_clusters"]["dm_ci95"] == expected_before["dm_ci95"]
    assert pair["before_game_id_clusters"]["dm_ci95"] == [0.09999999999999967, 0.10000000000000037]

    normalized = _PREREG.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    above, seal_line = normalized.split("\nSeal-SHA256-LF: ", maxsplit=1)
    assert seal_line.strip() == _SEAL
    assert hashlib.sha256((above + "\n").encode("utf-8")).hexdigest() == _SEAL
