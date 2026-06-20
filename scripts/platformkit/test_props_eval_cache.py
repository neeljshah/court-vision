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


# ---- Staleness guard: a cache computed under OLD settlement logic must NEVER
# ---- drive a PROVEN label (the void-fix regression that fabricated Saves).

def _write_payload(path, payload):
    with open(path, "w", encoding="ascii") as fh:
        json.dump(payload, fh)


def test_stale_cache_does_not_yield_proven(tmp_path):
    """A cache stamped with a DIFFERENT settle-logic version is refused PROVEN.

    Reproduces the live honesty bug: a genuine proven-grade stat (bss=0.34,
    n=662 -- the OLD fabricated Saves) computed under stale settlement logic must
    downgrade to unmeasured/MODEL_VIEW, never CALIBRATION_PROVEN.
    """
    out = os.path.join(str(tmp_path), "stale.json")
    _write_payload(out, {
        "settle_logic_version": "v0-OLD-fabricated",
        "per_stat": {"Saves": {"bss": 0.3365, "n": 662, "brier": 0.0175}},
    })
    cal = load_calibration(out)
    # Visible but flagged, and classify refuses to promote it.
    assert cal["Saves"].get("_stale_version") is True
    assert prop_tiering.classify("Saves", cal)[0] == "unmeasured"
    edge = prop_tiering.apply_tier(
        {"stat": "Saves", "reliable": True, "ev_flag": "ok"}, cal)
    assert edge["tier"] == "MODEL_VIEW"
    assert edge["calibration"] == "unmeasured"


def test_missing_version_stamp_is_treated_stale(tmp_path):
    """A pre-stamping cache (no settle_logic_version) cannot earn PROVEN either.

    The ORIGINAL bad cache had no version field; the guard must treat a missing
    stamp as a mismatch (None != live) so it can't slip a PROVEN through.
    """
    out = os.path.join(str(tmp_path), "nostamp.json")
    _write_payload(out, {
        "per_stat": {"Saves": {"bss": 0.3365, "n": 662}},
    })
    cal = load_calibration(out)
    assert cal["Saves"].get("_stale_version") is True
    assert prop_tiering.classify("Saves", cal)[0] == "unmeasured"


def test_fresh_cache_with_genuine_skill_still_proven(tmp_path):
    """A CURRENT-version cache with bss>=0.05, n>=100 still earns proven.

    The guard must not over-fire: a real, current proven-grade stat is promoted.
    """
    out = os.path.join(str(tmp_path), "fresh.json")
    _write_payload(out, {
        "settle_logic_version": prop_tiering.current_settle_version(),
        "per_stat": {"GoodStat": {"bss": 0.20, "n": 300}},
    })
    cal = load_calibration(out)
    assert not cal["GoodStat"].get("_stale_version")
    assert prop_tiering.classify("GoodStat", cal)[0] == "proven"
    edge = prop_tiering.apply_tier(
        {"stat": "GoodStat", "reliable": True, "ev_flag": "ok"}, cal)
    assert edge["tier"] == "CALIBRATION_PROVEN"


def test_void_fixed_eval_yields_no_fabricated_proven(tmp_path):
    """End-to-end: the void-fixed eval, freshly cached + reloaded, has NO proven.

    write_calibration_cache stamps the live version, so the reload is NOT stale;
    the absence of proven here is the HONEST post-void-fix result, not the guard.
    """
    out = os.path.join(str(tmp_path), "e2e.json")
    write_calibration_cache(_canned_df(), out_path=out)
    cal = load_calibration(out)
    # Not stale (freshly stamped), yet no stat clears proven on the canned data.
    assert not any(d.get("_stale_version") for d in cal.values())
    proven = [s for s in cal if prop_tiering.classify(s, cal)[0] == "proven"]
    assert proven == []


def test_payload_carries_version_stamp(tmp_path):
    """The written cache records the live settle-logic version."""
    out = os.path.join(str(tmp_path), "v.json")
    write_calibration_cache(_canned_df(), out_path=out)
    with open(out, "r", encoding="ascii") as fh:
        on_disk = json.load(fh)
    assert on_disk["settle_logic_version"] == prop_tiering.current_settle_version()
    assert on_disk["settle_logic_version"] is not None
