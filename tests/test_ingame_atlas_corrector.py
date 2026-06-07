"""Tests for the FLAGGED in-game atlas corrector (shadow path).

(a) DISABLED (default / CV_INGAME_ATLAS unset) -> output is byte-identical to base_rows.
(b) ENABLED  -> returns the SAME (player,stat) keys, each with a finite projected_final.

The enabled test does NOT assert the correction changes any value (it may legitimately
fall through to the raw projection when no leak-safe history / atlas exists in the test
env) -- only that the contract holds: same keys, all finite, never raises.
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("NBA_OFFLINE", "1")

from src.loop import ingame_atlas_corrector as iac  # noqa: E402


def _base_rows():
    return [
        {"player_id": 1629029, "stat": "pts", "projected_final": 24.0,
         "current": 12.0, "period": 2},
        {"player_id": 1629029, "stat": "reb", "projected_final": 8.0,
         "current": 4.0, "period": 2},
        {"player_id": 201939, "stat": "ast", "projected_final": 6.0,
         "current": 3.0, "period": 2},
        {"player_id": 201939, "stat": "blk", "projected_final": 1.0,
         "current": 0.0, "period": 2},
    ]


def _snapshot():
    return {
        "date": "2025-04-15",
        "period": 2,
        "home_team": "GSW",
        "away_team": "LAL",
        "players": [],
    }


@pytest.fixture(autouse=True)
def _clean_flag_and_cache(monkeypatch):
    monkeypatch.delenv("CV_INGAME_ATLAS", raising=False)
    iac.clear_corrector_cache()
    yield
    iac.clear_corrector_cache()


# ── (a) disabled => identical pass-through ───────────────────────────────────────
def test_disabled_is_noop_identity(monkeypatch):
    monkeypatch.delenv("CV_INGAME_ATLAS", raising=False)
    assert iac.is_enabled() is False
    base = _base_rows()
    out = iac.apply_atlas_correction(_snapshot(), base)
    # Pure pass-through: same object, byte-identical content.
    assert out is base
    assert out == _base_rows()


@pytest.mark.parametrize("val", ["0", "", "false", "no", "off", "nope"])
def test_falsey_flag_values_disable(monkeypatch, val):
    monkeypatch.setenv("CV_INGAME_ATLAS", val)
    assert iac.is_enabled() is False
    base = _base_rows()
    out = iac.apply_atlas_correction(_snapshot(), base)
    assert out is base


@pytest.mark.parametrize("val", ["1", "true", "TRUE", "yes", "on", "Y"])
def test_truthy_flag_values_enable(monkeypatch, val):
    monkeypatch.setenv("CV_INGAME_ATLAS", val)
    assert iac.is_enabled() is True


# ── (b) enabled => same keys, finite projected_final ─────────────────────────────
def test_enabled_same_keys_and_finite(monkeypatch):
    monkeypatch.setenv("CV_INGAME_ATLAS", "1")
    assert iac.is_enabled() is True
    base = _base_rows()
    out = iac.apply_atlas_correction(_snapshot(), base, device="cpu")

    base_keys = {(r["player_id"], r["stat"]) for r in base}
    out_keys = {(r["player_id"], r["stat"]) for r in out}
    assert out_keys == base_keys

    assert len(out) == len(base)
    for r in out:
        pf = r.get("projected_final")
        assert pf is not None
        assert isinstance(pf, float) or isinstance(pf, int)
        assert math.isfinite(float(pf))


def test_enabled_no_leak_boundary_passthrough(monkeypatch):
    """Enabled but the snapshot carries no date -> safe no-op pass-through."""
    monkeypatch.setenv("CV_INGAME_ATLAS", "1")
    snap = {"period": 2, "players": []}  # no date/game_date/start_time
    base = _base_rows()
    out = iac.apply_atlas_correction(snap, base, device="cpu")
    assert out is base


def test_enabled_empty_rows(monkeypatch):
    monkeypatch.setenv("CV_INGAME_ATLAS", "1")
    out = iac.apply_atlas_correction(_snapshot(), [], device="cpu")
    assert out == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
