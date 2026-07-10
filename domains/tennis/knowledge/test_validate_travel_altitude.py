"""Per-file test for knowledge.validate_travel_altitude. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/tennis/knowledge/test_validate_travel_altitude.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.tennis.knowledge import validate_travel_altitude as vta

_REQUIRED_KEYS = {"hypothesis", "n", "effect", "p", "note"}


def _synthetic_travel(n_events=40, seed=1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_events):
        eid = "e%d" % i
        alt = float(rng.choice([10.0, 20.0, 600.0, 700.0]))
        rows.append({"event_id": eid, "player": "P1_%d" % i, "is_p1": True,
                      "miles_flown_in": float(rng.uniform(0, 3000)), "venue_altitude_m": alt})
        rows.append({"event_id": eid, "player": "P2_%d" % i, "is_p1": False,
                      "miles_flown_in": float(rng.uniform(0, 3000)), "venue_altitude_m": alt})
    return pd.DataFrame(rows)


def _synthetic_match_stats(n_events=40, seed=2) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_events):
        rows.append({"event_id": "e%d" % i, "p1_ace_rate": float(rng.uniform(0.02, 0.15)),
                      "p2_ace_rate": float(rng.uniform(0.02, 0.15))})
    return pd.DataFrame(rows)


def _synthetic_matches(n_events=40, seed=3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_events):
        rows.append({"event_id": "e%d" % i, "p1_rank": int(rng.integers(1, 200)),
                      "p2_rank": int(rng.integers(1, 200)), "winner": int(rng.choice([1, 2]))})
    return pd.DataFrame(rows)


def test_hypothesis_functions_happy_path_shape_without_verdict_key():
    """These functions deliberately do NOT set 'verdict' -- run() adds it
    afterwards."""
    travel = _synthetic_travel()
    stats_df = _synthetic_match_stats()
    matches = _synthetic_matches()
    r1 = vta.altitude_effect_on_serve_ace_rate(travel, stats_df)
    assert _REQUIRED_KEYS <= set(r1) and "verdict" not in r1
    r2 = vta.long_travel_effect_on_win_prob_partial(travel, matches)
    assert _REQUIRED_KEYS <= set(r2) and "verdict" not in r2


def test_verdict_nan_p_is_not_testable():
    assert vta._verdict(float("nan"), 0.05, 0.02) == "NOT_TESTABLE"
    assert vta._verdict(0.001, 0.05, 0.02) == "CONFIRMED_LOCAL"
    assert vta._verdict(0.5, 0.05, 0.02) == "NULL_LOCAL"


def test_travel_matches_frame_computes_signed_diff():
    """Failure mode: a sign flip in travel_diff_1000mi would silently invert
    the direction of every downstream coefficient."""
    travel = pd.DataFrame({
        "event_id": ["e1", "e1"], "player": ["A", "B"], "is_p1": [True, False],
        "miles_flown_in": [3000.0, 1000.0], "venue_altitude_m": [10.0, 10.0],
    })
    matches = pd.DataFrame({"event_id": ["e1"], "p1_rank": [5], "p2_rank": [50], "winner": [1]})
    fr = vta._travel_matches_frame(travel, matches)
    assert len(fr) == 1
    assert fr["travel_diff_1000mi"].iloc[0] == 2.0  # p1 traveled 2000mi further


def test_run_stamps_verdict_and_writes_two_edge_free_rows(tmp_path, monkeypatch):
    ledger = tmp_path / "validation_ledger.jsonl"
    monkeypatch.setattr(vta, "LEDGER_PATH", ledger)
    monkeypatch.setattr(vta, "load_travel_scouting", _synthetic_travel)
    monkeypatch.setattr(vta, "load_match_stats", _synthetic_match_stats)
    monkeypatch.setattr(vta, "load_matches", _synthetic_matches)
    rows = vta.run()
    assert len(rows) == 2
    assert all("verdict" in r and r["verdict"] in
               {"CONFIRMED_LOCAL", "NULL_LOCAL", "NOT_TESTABLE"} for r in rows)
    assert all(r["edge_claimed"] is False and r["sport"] == "tennis" for r in rows)
    on_disk = [l for l in ledger.read_text(encoding="ascii").splitlines() if l.strip()]
    assert len(on_disk) == 2
