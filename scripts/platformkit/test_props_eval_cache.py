"""Per-file tests for the calibration cache (props_eval + prop_tiering).

  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_props_eval_cache.py -q
"""
from __future__ import annotations

import json
import os

import pandas as pd

from scripts.platformkit import prop_tiering
from scripts.platformkit.props_eval import (
    write_calibration_cache,
    load_calibration,
)


def _canned_df():
    """4 dated matches, 2 players, so the backtest yields real predictions."""
    rows = []
    cols_zero = {
        "shotsOnTarget": 0.0, "foulsCommitted": 0.0, "foulsSuffered": 0.0,
        "yellowCards": 0.0, "redCards": 0.0, "goalAssists": 0.0, "offsides": 0.0,
        "totalGoals": 0.0, "saves": 0.0,
    }
    plan = [
        ("E1", "2026-01-01", "A", 90, 3.0), ("E1", "2026-01-01", "B", 90, 0.0),
        ("E2", "2026-01-05", "A", 90, 4.0), ("E2", "2026-01-05", "B", 90, 1.0),
        ("E3", "2026-01-09", "A", 90, 2.0), ("E3", "2026-01-09", "B", 90, 0.0),
        ("E4", "2026-01-13", "A", 90, 5.0), ("E4", "2026-01-13", "B", 90, 0.0),
    ]
    for eid, date, pid, mins, shots in plan:
        r = {"event_id": eid, "date": date, "player_id": pid, "position": "F",
             "minutes": float(mins), "totalShots": float(shots)}
        r.update(cols_zero)
        rows.append(r)
    return pd.DataFrame(rows)


def test_write_cache_writes_per_stat_bss(tmp_path):
    out = os.path.join(str(tmp_path), "calib.json")
    df = _canned_df()
    payload = write_calibration_cache(df, out_path=out)
    assert payload["written"] is True
    assert os.path.exists(out)
    with open(out, "r", encoding="ascii") as fh:
        on_disk = json.load(fh)
    assert "per_stat" in on_disk
    assert on_disk["mode"] == "strict leak-free"
    # Each cached stat carries a bss + n.
    for stat, d in on_disk["per_stat"].items():
        assert "bss" in d
        assert "n" in d and d["n"] > 0


def test_load_calibration_round_trips(tmp_path):
    out = os.path.join(str(tmp_path), "calib.json")
    write_calibration_cache(_canned_df(), out_path=out)
    loaded = load_calibration(out)
    assert isinstance(loaded, dict)
    assert len(loaded) > 0
    # round-trips the same per-stat keys + bss values
    for stat, d in loaded.items():
        assert "bss" in d


def test_missing_file_returns_empty():
    assert load_calibration(os.path.join("nope", "absent.json")) == {}


def test_classify_thresholds():
    cal = {
        "Saves": {"bss": 0.3, "n": 662},
        "Fouls": {"bss": 0.03, "n": 662},
        "Shots On Target": {"bss": -0.05, "n": 662},
        "ThinStat": {"bss": 0.2, "n": 10},      # proven margin but too few n
        "NoBss": {"n": 100},                     # missing bss -> unmeasured
    }
    assert prop_tiering.classify("Saves", cal)[0] == "proven"
    assert prop_tiering.classify("Fouls", cal)[0] == "marginal"
    assert prop_tiering.classify("Shots On Target", cal)[0] == "weak"
    assert prop_tiering.classify("ThinStat", cal)[0] == "marginal"  # n<100
    assert prop_tiering.classify("NoBss", cal)[0] == "unmeasured"
    assert prop_tiering.classify("Absent", cal)[0] == "unmeasured"


def test_write_cache_bad_input_never_raises(tmp_path):
    out = os.path.join(str(tmp_path), "calib.json")
    payload = write_calibration_cache(pd.DataFrame(), out_path=out)
    # empty df -> backtest yields no predictions; still returns a payload, no raise
    assert "per_stat" in payload
    assert payload["overall"]["n"] == 0
