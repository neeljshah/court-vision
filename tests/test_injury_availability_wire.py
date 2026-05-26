"""tests/test_injury_availability_wire.py — R15_W1.

Tests for the inference-time ESPN injury-feed wiring:

  1. OUT       player → final q50 == 0.0 (band collapses to 0/0/0).
  2. PROBABLE  player → final q50 == 0.9 × raw_q50.
  3. Player not in feed → final q50 == raw_q50 (default factor 1.0).
  4. Stale snapshot (>6h old) → fresh scrape is triggered (mocked).
  5. NOT WITH TEAM player → final q50 == 0.0.
  6. Disable env var (NBA_INJURY_WIRE_DISABLE=1) → bypass.
  7. Name fallback when player_id is unknown.
  8. q10/q90 None passthrough.

All tests stub the snapshot loader with a tmp-path JSON. None of these hit
the network.
"""
from __future__ import annotations

import json
import os
import sys
import time

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.prediction import injury_availability as ia  # noqa: E402


# ── helpers ──────────────────────────────────────────────────────────────────

def _write_snapshot(tmp_path, players: list, *, date_str: str = "2026-05-26",
                    fresh: bool = True) -> str:
    """Write a snapshot JSON to tmp_path/data/cache/ and return its path.

    When ``fresh`` is False, the file's mtime is back-dated by 12 hours so
    the stale-check fires.
    """
    cache_dir = tmp_path / "data" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "date":       date_str,
        "source":     "espn_public_api",
        "fetched_at": "2026-05-26T08:00:33",
        "n_players":  len(players),
        "players":    players,
    }
    fpath = cache_dir / f"injury_status_{date_str}.json"
    fpath.write_text(json.dumps(payload), encoding="utf-8")
    if not fresh:
        old = time.time() - (12 * 3600)
        os.utime(fpath, (old, old))
    return str(fpath)


@pytest.fixture(autouse=True)
def _wire_tmp_cache_dir(tmp_path, monkeypatch):
    """Point the injury module at a clean per-test tmp cache directory
    and flush the in-process cache before EVERY test.
    """
    monkeypatch.setattr(ia, "_CACHE_DIR", str(tmp_path / "data" / "cache"))
    monkeypatch.delenv(ia._DISABLE_ENV, raising=False)
    ia.reset_cache()
    yield
    ia.reset_cache()


# ── 1. OUT collapses to zero ─────────────────────────────────────────────────

def test_out_player_zeroes_q50(tmp_path):
    _write_snapshot(tmp_path, players=[{
        "player_name": "Jayson Tatum", "team": "BOS", "status": "OUT",
        "player_id": 1628369, "availability_factor": 0.0,
    }])

    q50, q10, q90 = ia.apply_availability(1628369, q50=22.5, q10=15.0, q90=30.0)
    assert q50 == 0.0
    assert q10 == 0.0
    assert q90 == 0.0


# ── 2. PROBABLE dampens by 0.9 ──────────────────────────────────────────────

def test_probable_player_scales_q50_by_0_9(tmp_path):
    _write_snapshot(tmp_path, players=[{
        "player_name": "Anthony Edwards", "team": "MIN", "status": "PROBABLE",
        "player_id": 1630162, "availability_factor": 0.9,
    }])

    raw = 28.4
    q50, _, _ = ia.apply_availability(1630162, q50=raw)
    assert q50 == pytest.approx(raw * 0.9)


# ── 3. Player not in feed → default 1.0 ─────────────────────────────────────

def test_player_not_in_feed_default_one(tmp_path):
    _write_snapshot(tmp_path, players=[{
        "player_name": "Some Other Guy", "team": "ATL", "status": "OUT",
        "player_id": 9999999, "availability_factor": 0.0,
    }])

    raw = 18.7
    q50, q10, q90 = ia.apply_availability(1234567, q50=raw, q10=10.0, q90=25.0)
    # Unknown player → factor 1.0
    assert q50 == raw
    assert q10 == 10.0
    assert q90 == 25.0


# ── 4. Stale snapshot triggers fresh scrape ─────────────────────────────────

def test_stale_snapshot_triggers_fresh_scrape(tmp_path, monkeypatch):
    """A snapshot older than _STALE_HOURS must cause _trigger_fresh_scrape()
    to fire. We don't actually shell out — we patch the function and assert
    it was called.
    """
    _write_snapshot(tmp_path,
                    players=[{"player_name": "X", "team": "BOS",
                              "status": "OUT", "player_id": 1,
                              "availability_factor": 0.0}],
                    fresh=False)

    call_log: list = []

    def fake_scrape():
        call_log.append(True)
        # Touch the file so it becomes "fresh" after the call.
        snap = ia._latest_snapshot_path()
        if snap:
            os.utime(snap, None)
        return True

    monkeypatch.setattr(ia, "_trigger_fresh_scrape", fake_scrape)

    # First access — must trip the staleness check and call fake_scrape.
    ia.reset_cache()
    factor = ia.get_availability_factor(player_id=1)
    assert call_log == [True], "stale snapshot did not trigger fresh scrape"
    assert factor == 0.0       # OUT


# ── 5. NOT WITH TEAM zeroes the band ────────────────────────────────────────

def test_not_with_team_collapses_band(tmp_path):
    _write_snapshot(tmp_path, players=[{
        "player_name": "Suspended Star", "team": "PHI", "status": "NOT WITH TEAM",
        "player_id": 4242, "availability_factor": 0.0,
    }])

    q50, q10, q90 = ia.apply_availability(4242, q50=24.0, q10=18.0, q90=31.0)
    assert (q50, q10, q90) == (0.0, 0.0, 0.0)


# ── 6. Disable env-var bypass ───────────────────────────────────────────────

def test_disable_env_var_bypasses_wire(tmp_path, monkeypatch):
    _write_snapshot(tmp_path, players=[{
        "player_name": "Out Player", "team": "BOS", "status": "OUT",
        "player_id": 7, "availability_factor": 0.0,
    }])

    monkeypatch.setenv(ia._DISABLE_ENV, "1")
    ia.reset_cache()

    factor = ia.get_availability_factor(player_id=7)
    assert factor == 1.0, "disable env did not bypass the wire"


# ── 7. Name fallback when player_id missing ─────────────────────────────────

def test_name_fallback(tmp_path):
    _write_snapshot(tmp_path, players=[{
        "player_name": "Nikola Jokić",     # accent
        "team": "DEN", "status": "QUESTIONABLE",
        "player_id": None, "availability_factor": 0.6,
    }])

    # Look up using ASCII variant — _name_key strips diacritics.
    factor = ia.get_availability_factor(player_id=None,
                                        player_name="Nikola Jokic")
    assert factor == 0.6


# ── 8. apply_availability with q10/q90 None still works ─────────────────────

def test_apply_availability_q10_q90_optional(tmp_path):
    _write_snapshot(tmp_path, players=[{
        "player_name": "X", "team": "BOS", "status": "DOUBTFUL",
        "player_id": 100, "availability_factor": 0.3,
    }])

    q50, q10, q90 = ia.apply_availability(100, q50=20.0)
    assert q50 == pytest.approx(6.0)
    assert q10 is None
    assert q90 is None
