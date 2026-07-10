"""Per-file test for knowledge.validate_point_dynamics. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/tennis/knowledge/test_validate_point_dynamics.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.tennis.knowledge import validate_point_dynamics as vpd

_REQUIRED_KEYS = {"hypothesis", "n", "effect", "p", "note"}


def _synthetic_points(n_per_match=60, n_matches=2, seed=4) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for m in range(n_matches):
        match_id = "m%d" % m
        for i in range(n_per_match):
            set_no = 1 + (i // 15)
            rows.append({
                "match_id": match_id, "point_number": i + 1, "set_no": set_no,
                "game_no": 1 + (i // 4), "surface": "Clay" if i % 2 == 0 else "Grass",
                "point_server": "P1" if i % 2 == 0 else "P2",
                "point_winner": "P1" if i % 3 == 0 else "P2",
                "rally": float(rng.integers(1, 10)),
                "speed_kmh": float(rng.uniform(140, 200)),
                "p1_double_fault": 1 if i % 20 == 0 else 0,
                "p2_double_fault": 1 if i % 25 == 0 else 0,
            })
    return pd.DataFrame(rows)


def test_hypothesis_functions_happy_path_shape_without_verdict_key():
    """These functions deliberately do NOT set 'verdict' -- run() adds it
    afterwards. A test that expects 'verdict' here would be testing the
    wrong contract."""
    df = _synthetic_points()
    for fn in (vpd.serve_advantage_by_surface, vpd.rally_length_clay_vs_grass,
               vpd.serve_speed_decay_within_match, vpd.double_fault_rate_by_set_number,
               vpd.deciding_set_hold_rate_shift):
        r = fn(df)
        assert _REQUIRED_KEYS <= set(r), fn.__name__
        assert "verdict" not in r, fn.__name__


def test_verdict_nan_p_is_not_testable():
    assert vpd._verdict(float("nan"), 0.5, 0.15) == "NOT_TESTABLE"
    assert vpd._verdict(0.001, 0.5, 0.15) == "CONFIRMED_LOCAL"
    assert vpd._verdict(0.5, 0.5, 0.15) == "NULL_LOCAL"


def test_run_stamps_verdict_and_writes_five_edge_free_rows(tmp_path, monkeypatch):
    """Failure mode: run() is the only place 'verdict' gets attached -- if
    that wiring breaks, rows would land in the ledger missing a verdict
    field, and nothing downstream would notice until a reader crashed."""
    ledger = tmp_path / "validation_ledger.jsonl"
    monkeypatch.setattr(vpd, "LEDGER_PATH", ledger)
    monkeypatch.setattr(vpd, "load_slam_points", lambda: _synthetic_points())
    rows = vpd.run()
    assert len(rows) == 5
    assert all("verdict" in r and r["verdict"] in
               {"CONFIRMED_LOCAL", "NULL_LOCAL", "NOT_TESTABLE"} for r in rows)
    assert all(r["edge_claimed"] is False and r["sport"] == "tennis" for r in rows)
    on_disk = [l for l in ledger.read_text(encoding="ascii").splitlines() if l.strip()]
    assert len(on_disk) == 5
