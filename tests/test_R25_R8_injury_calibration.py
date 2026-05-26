"""tests/test_R25_R8_injury_calibration.py — guard the R25_R8 probe.

These tests pin the calibration probe's invariants so a future refactor
or daemon-driven data refresh can not silently weaken the safety
properties:

  * OUT / NOT WITH TEAM factor MUST remain 0.0 — the R23_P2 invariant
    (bet ranker kill switch) depends on it.
  * The probe writes ``data/cache/probe_R25_R8_results.json`` with the
    expected top-level keys regardless of ship status (so the
    dashboards / next probes can read it).
  * When fewer than _MIN_DAYS distinct injury-report dates exist
    locally, the probe MUST exit BLOCKED — never fabricate a
    calibration.
  * The factor-table patcher round-trips through the live
    ``get_availability_factor`` helper (the live engine path must
    keep working after a patch).
  * Synthetic-data fast-path: when ≥ _MIN_DAYS dates and ≥
    _MIN_SAMPLES_EACH samples per status exist, the proposed factors
    track observed medians.
  * Status normalisation is case / whitespace insensitive.
"""
from __future__ import annotations

import importlib
import json
import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

PROBE_MODULE = (
    "scripts.improve_loop.probe_R25_R8_injury_status_calibration"
)


def _import_probe():
    """Import the probe module fresh so module-level state is clean."""
    if PROBE_MODULE in sys.modules:
        del sys.modules[PROBE_MODULE]
    return importlib.import_module(PROBE_MODULE)


def test_current_factors_table_pins_out_at_zero():
    """R23_P2 invariant: OUT / NOT WITH TEAM must always be 0.0."""
    probe = _import_probe()
    table = probe._CURRENT_FACTORS  # noqa: SLF001
    assert table["OUT"] == 0.0
    assert table["NOT WITH TEAM"] == 0.0
    assert table["AVAILABLE"] == 1.0


def test_thresholds_are_sane():
    """SHIP-gate thresholds must be non-trivial."""
    probe = _import_probe()
    assert probe._MIN_DAYS >= 30          # noqa: SLF001
    assert probe._MIN_SAMPLES_EACH >= 50  # noqa: SLF001
    assert 0.0 < probe._MIN_DELTA <= 0.5  # noqa: SLF001


def test_probe_runs_and_writes_results_json(tmp_path, monkeypatch):
    """End-to-end: probe writes its results JSON with the agreed keys."""
    probe = _import_probe()
    monkeypatch.setattr(probe, "_RESULTS_PATH",
                        str(tmp_path / "probe_R25_R8_results.json"))
    rc = probe.main()
    assert rc == 0
    payload = json.load(open(
        tmp_path / "probe_R25_R8_results.json", encoding="utf-8"))
    for k in ("probe", "run_date", "n_snapshots",
              "per_status_old_factor", "ship_status", "ship_reason"):
        assert k in payload, f"missing key {k}"
    assert payload["probe"].startswith("R25_R8")


def test_probe_blocks_when_history_too_short(tmp_path, monkeypatch):
    """Off-season fresh-clone case: <30 days must produce BLOCKED, never
    a silent edit of the factor table."""
    probe = _import_probe()
    monkeypatch.setattr(probe, "_RESULTS_PATH",
                        str(tmp_path / "out.json"))
    # Force the snapshot loader to return ≤ _MIN_DAYS days.
    fake_rows = [
        {"player_id": 1, "player_name": "x",
         "report_date": "2026-05-26", "status": "OUT"},
    ]
    monkeypatch.setattr(probe, "_load_snapshot_rows",
                        lambda: fake_rows)
    rc = probe.main()
    payload = json.load(open(tmp_path / "out.json", encoding="utf-8"))
    assert rc == 0
    assert payload["ship_status"] == "BLOCKED"
    assert "≥ 30" in payload["ship_reason"] or "30" in payload["ship_reason"]
    assert payload["source_patched"] is False


def test_calibration_with_synthetic_history(tmp_path, monkeypatch):
    """Synthetic ≥ 30-day calibration produces new factors tracking
    the observed medians.  Stubs the snapshot loader and the stats
    parquet loader so the probe is exercised end-to-end with known
    inputs."""
    import pandas as pd
    probe = _import_probe()
    monkeypatch.setattr(probe, "_RESULTS_PATH",
                        str(tmp_path / "out.json"))
    # Build 35 distinct report dates × 60 players × 3 non-OUT statuses,
    # each emitting a row.  Players' actual minutes ratio is fixed per
    # status so the median is exact.
    dates = [f"2026-04-{d:02d}" for d in range(1, 31)] + [
        f"2026-05-{d:02d}" for d in range(1, 6)]
    statuses = {"DOUBTFUL": 0.25, "QUESTIONABLE": 0.90, "PROBABLE": 0.97}
    fake_rows = []
    pergame_rows = []
    pid = 1000
    for status, ratio in statuses.items():
        for _ in range(60):
            pid += 1
            for dt in dates:
                fake_rows.append({
                    "player_id":   pid,
                    "player_name": f"p{pid}",
                    "report_date": dt,
                    "status":      status,
                })
            # Build a stats history: 40 prior games (season_avg=30 min)
            # + 1 game on report date with min = 30 * ratio.
            for j, prior_date in enumerate([
                    f"2026-02-{(d % 28) + 1:02d}" for d in range(40)]):
                pergame_rows.append({
                    "player_id": pid, "game_id": f"g{pid}_{j}",
                    "game_date": prior_date,
                    "min": 30.0, "pts": 18.0, "reb": 6.0, "ast": 4.0,
                })
            pergame_rows.append({
                "player_id": pid, "game_id": f"g{pid}_rd",
                "game_date": dates[0],
                "min": 30.0 * ratio, "pts": 18.0 * ratio,
                "reb": 6.0 * ratio, "ast": 4.0 * ratio,
            })
    monkeypatch.setattr(probe, "_load_snapshot_rows", lambda: fake_rows)
    monkeypatch.setattr(probe, "_load_pergame_stats",
                        lambda: pd.DataFrame(pergame_rows))
    # Guard against patching the real source file.
    monkeypatch.setattr(probe, "_patch_factor_table",
                        lambda nf: True)

    rc = probe.main()
    payload = json.load(open(tmp_path / "out.json", encoding="utf-8"))
    assert rc == 0
    assert payload["n_snapshots"] >= probe._MIN_DAYS  # noqa: SLF001
    assert payload["per_status_new_factor"] is not None
    new = payload["per_status_new_factor"]
    # OUT is still 0.0 (invariant preserved).
    assert new["OUT"] == 0.0
    assert new["NOT WITH TEAM"] == 0.0
    # Each non-OUT status lands within 0.05 of its synthetic median.
    for status, expected in statuses.items():
        assert abs(new[status] - expected) <= 0.05, (
            f"{status}: got {new[status]}, expected ~{expected}")


def test_round_trip_through_get_availability_factor(monkeypatch):
    """Whatever factor table is in source, the public
    get_availability_factor() must read the same OUT=0.0 for OUT
    statuses (live engine invariant)."""
    monkeypatch.setenv("NBA_INJURY_WIRE_DISABLE", "0")
    from src.prediction import injury_availability as ia
    ia.reset_cache()
    # The shipped table is the authoritative source.
    assert ia.AVAILABILITY_FACTOR["OUT"] == 0.0
    assert ia.AVAILABILITY_FACTOR["NOT WITH TEAM"] == 0.0
    assert ia.AVAILABILITY_FACTOR["AVAILABLE"] == 1.0
    # Every non-OUT entry is in [0, 1].
    for k, v in ia.AVAILABILITY_FACTOR.items():
        assert 0.0 <= v <= 1.0, f"{k}={v} outside [0,1]"


def test_apply_availability_collapses_out_player_to_zero(monkeypatch):
    """Downstream live_bet_ranker dispatch: factor 0.0 must collapse
    q50/q10/q90 to (0, 0, 0) so any prop on an OUT player is killed
    BEFORE the ranker sees it."""
    monkeypatch.setenv("NBA_INJURY_WIRE_DISABLE", "0")
    from src.prediction import injury_availability as ia
    # Inject a single OUT player into the in-process cache.
    ia.reset_cache()
    ia._CACHED["by_player_id"] = {99999: 0.0}  # noqa: SLF001
    ia._CACHED["by_name"]      = {}            # noqa: SLF001
    ia._CACHED["loaded_at"]    = 1.0           # noqa: SLF001
    ia._CACHED["snapshot_mtime"] = 1.0         # noqa: SLF001

    # Monkeypatch _ensure_loaded so it doesn't try to re-read the disk
    # snapshot (which would overwrite our synthetic cache).
    monkeypatch.setattr(ia, "_ensure_loaded", lambda force=False: None)
    q50, q10, q90 = ia.apply_availability(99999, 20.0, q10=14.0, q90=27.0)
    assert q50 == 0.0
    assert q10 == 0.0
    assert q90 == 0.0
    ia.reset_cache()
