"""tests.platformkit.combo.test_null_floor_s40b -- RT-9: the n_extra ceiling is labelled.

Per-file only (a full pytest run freezes the box). ASCII; stdlib + numpy.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parents[3]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from scripts.platformkit.combo import null_floor as NF  # noqa: E402


def _cached_floor(tmp_path: Path, monkeypatch) -> None:
    """Write a floor table whose p99 RISES with n_extra -- more free columns, more noise."""
    payload = {"sport": "fake", "m_draws": 40, "base_seed": 0, "floors": {
        "unit_a": {str(n): {"p50": 0.0, "p90": 0.0, "p99": 0.001 * n, "m": 40,
                            "base_seed": 0, "n_extra_params": n}
                   for n in range(1, NF.MAX_EXTRA_PARAMS + 1)}}}
    path = tmp_path / "null_floor_fake.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(NF, "_floor_path", lambda sport: path)


def test_s40b_rt9_over_ceiling_n_extra_raises_instead_of_grading_against_a_lower_floor(
        tmp_path, monkeypatch):
    """RT-9: `n_key = str(min(max(1, n), MAX_EXTRA_PARAMS))` silently CLAMPED. Measured
    before the fix: n_extra=12 -> table key "4", so a 12-column noise candidate was graded
    against the 4-column floor -- which sits lower -- and returned PROCEED."""
    _cached_floor(tmp_path, monkeypatch)
    over = NF.MAX_EXTRA_PARAMS + 8                      # the memo's n_extra=12 at MAX=4
    clamped_floor = 0.001 * NF.MAX_EXTRA_PARAMS         # the floor the clamp used to reach
    delta = clamped_floor + 1e-9                        # just above it -> the old PROCEED

    with pytest.raises(KeyError) as exc:
        NF.prescreen_verdict("fake", "unit_a", over, delta)
    assert "not a clamp" in str(exc.value)
    assert str(over) in str(exc.value)


def test_s40b_rt9_covered_n_extra_still_grades_against_its_own_floor(tmp_path, monkeypatch):
    """Every n_extra the table actually covers is unchanged, and each grades against ITS
    own p99 -- derived here from the fixture, not read back out of the module."""
    _cached_floor(tmp_path, monkeypatch)
    for n in range(1, NF.MAX_EXTRA_PARAMS + 1):
        own_p99 = 0.001 * n
        assert NF.prescreen_verdict("fake", "unit_a", n, own_p99) == "REJECT"
        assert NF.prescreen_verdict("fake", "unit_a", n, own_p99 * 2 + 1.0) == "PROCEED"
    # n_extra=0 is not a coverage gap to round up from either.
    with pytest.raises(KeyError):
        NF.prescreen_verdict("fake", "unit_a", 0, 0.5)
