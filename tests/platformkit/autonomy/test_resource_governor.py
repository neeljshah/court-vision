"""tests for scripts.platformkit.autonomy.resource_governor -- fail-safe gate.

Low/unknown headroom must return the DISTINCT status DEFERRED_RESOURCE (an
under-run), never PROCEED, and never a reject/plateau string. Run ONLY this file:
    python -m pytest tests/platformkit/autonomy/test_resource_governor.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.autonomy.resource_governor import (  # noqa: E402
    DEFERRED_RESOURCE,
    PROCEED,
    R_HIGH_CPU,
    R_LOW_MEM,
    R_PSUTIL_MISSING,
    R_UNKNOWN,
    ResourceGovernor,
    decide,
    probe_reading,
)


def test_ample_headroom_proceeds():
    d = decide({"mem_free_frac": 0.50, "cpu_frac": 0.30})
    assert d["status"] == PROCEED


def test_low_memory_defers_with_distinct_status():
    d = decide({"mem_free_frac": 0.05})
    assert d["status"] == DEFERRED_RESOURCE
    assert d["reason"] == R_LOW_MEM
    # DISTINCT: never confusable with PROCEED.
    assert d["status"] != PROCEED


def test_high_cpu_defers():
    d = decide({"mem_free_frac": 0.50, "cpu_frac": 0.99})
    assert d["status"] == DEFERRED_RESOURCE
    assert d["reason"] == R_HIGH_CPU


def test_unknown_headroom_fails_safe_to_defer():
    """Missing / None reading -> UNKNOWN -> DEFER (under-run, not charge ahead)."""
    assert decide(None)["status"] == DEFERRED_RESOURCE
    assert decide({})["status"] == DEFERRED_RESOURCE
    assert decide({"mem_free_frac": None})["status"] == DEFERRED_RESOURCE
    assert decide({"mem_free_frac": "bad"})["status"] == DEFERRED_RESOURCE
    for r in (decide(None), decide({})):
        assert r["reason"] == R_UNKNOWN


def test_out_of_range_mem_defers():
    assert decide({"mem_free_frac": 1.7})["status"] == DEFERRED_RESOURCE
    assert decide({"mem_free_frac": -0.2})["status"] == DEFERRED_RESOURCE


def test_deferred_status_is_not_a_reject_or_plateau_word():
    """The under-run status must NOT collide with reject/plateau vocabulary so it
    can never be misread as 'model has nothing left to learn'."""
    d = decide({"mem_free_frac": 0.01})
    s = d["status"].lower()
    for forbidden in ("reject", "plateau", "no_edge", "proceed", "ready", "ship"):
        assert forbidden not in s
    assert d["status"] == DEFERRED_RESOURCE


def test_governor_psutil_missing_defers():
    """No psutil + probe returns None -> DEFERRED_RESOURCE (psutil_missing)."""
    gov = ResourceGovernor(probe=lambda: None)
    d = gov.check()
    assert d["status"] == DEFERRED_RESOURCE
    assert d["reason"] == R_PSUTIL_MISSING


def test_governor_with_fake_psutil_proceeds():
    class _VM:
        total = 16 * 1024**3
        available = 8 * 1024**3

    class _FakePsutil:
        def virtual_memory(self):
            return _VM()

        def cpu_percent(self, interval=0.0):
            return 20.0

    gov = ResourceGovernor(psutil_mod=_FakePsutil())
    d = gov.check()
    assert d["status"] == PROCEED


def test_probe_reading_handles_zero_total():
    class _VM:
        total = 0
        available = 0

    class _Bad:
        def virtual_memory(self):
            return _VM()

    assert probe_reading(_Bad()) is None  # -> decide(None) defers


def test_governor_probe_raising_defers():
    def boom():
        raise RuntimeError("probe blew up")

    # probe raises + psutil_mod was given (so not 'missing') -> UNKNOWN defer.
    gov = ResourceGovernor(probe=boom, psutil_mod=object())
    d = gov.check()
    assert d["status"] == DEFERRED_RESOURCE
