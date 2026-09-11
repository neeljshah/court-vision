"""G378: the sealed cue's decision rule, the two controls, the even sampler and the seal.

Run this file ALONE. A full suite is never run in this repository.
The character route is never called here: a stub detector stands in for it so the test is fast,
deterministic and does not need the model weights.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from scripts.platformkit.tracking import g334_seal, g378_cue, g378_sample, g378_sheets

PREREG = Path("docs/evidence/tracking/g378_orientation_cue_2026-09-10/g378_prereg_2026-09-10.md")
BRIGHT = 240


def _stub_detections(frame):
    """One unit detection per bright column band, so a flip genuinely flips the masses."""
    top, bottom = g378_cue.band_bounds(frame.shape[0])
    band = frame[top:bottom, :]
    if band.size == 0:
        return []
    columns = np.where(band.mean(axis=(0, 2)) > 200)[0]
    return [(float(column), 1000.0) for column in columns]


@pytest.fixture(autouse=True)
def stub(monkeypatch):
    monkeypatch.setattr(g378_cue, "_detections", _stub_detections)
    monkeypatch.setitem(g378_cue._ROUTE, "conf_min", 0.30)
    monkeypatch.setitem(g378_cue._ROUTE, "top_frac", 0.10)
    monkeypatch.setitem(g378_cue._ROUTE, "module_file", "stub")


def _frame(left_width: int, right_width: int, height: int = 400, width: int = 800):
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    top, bottom = int(0.10 * height), int(g378_cue.BOTTOM_FRAC * height)
    if left_width:
        frame[top:bottom, 10:10 + left_width] = BRIGHT
    if right_width:
        frame[top:bottom, width - 10 - right_width:width - 10] = BRIGHT
    return frame


def test_rule_calls_the_heavier_side():
    assert g378_cue.call(_frame(40, 4))["call"] == "LEFT"
    assert g378_cue.call(_frame(4, 40))["call"] == "RIGHT"


def test_unknown_when_evidence_is_missing_or_balanced():
    assert g378_cue.call(_frame(0, 0))["unknown_reason"] == "no_detection"
    assert g378_cue.call(None)["unknown_reason"] == "no_frame"
    balanced = g378_cue.call(_frame(20, 20))
    assert balanced["call"] == "UNKNOWN" and balanced["unknown_reason"] == "ratio_below_margin"
    thin = g378_cue.call(_frame(1, 0))
    assert thin["call"] == "UNKNOWN" and thin["unknown_reason"] == "mass_below_floor"


def test_mirror_control_flips_the_call():
    for left, right in ((40, 4), (4, 40), (60, 10)):
        frame = _frame(left, right)
        base = g378_cue.call(frame)["call"]
        assert base in ("LEFT", "RIGHT")
        assert g378_cue.call(g378_cue.mirrored(frame))["call"] == \
            {"LEFT": "RIGHT", "RIGHT": "LEFT"}[base]


def test_masked_control_yields_unknown():
    frame = _frame(60, 4)
    assert g378_cue.call(frame)["call"] == "LEFT"
    assert g378_cue.call(g378_cue.masked(frame))["call"] == "UNKNOWN"
    top, bottom = g378_cue.band_bounds(frame.shape[0])
    assert (g378_cue.masked(frame)[top:bottom, :] == g378_cue.MASK_VALUE).all()
    assert (g378_cue.masked(frame)[:top, :] == frame[:top, :]).all()


def test_even_sampler_is_never_a_head_slice():
    items = list(range(240))
    picked = g378_sheets._even(items, 30)
    assert len(picked) == 30
    assert picked[0] == 0 and picked[-1] >= 232
    assert picked != items[:30]
    assert len(set(picked)) == 30
    assert g378_sheets._even(items, 300) == items
    assert g378_sheets._even([], 30) == []


def test_ticks_are_interior_and_evenly_spaced():
    indices = g378_sample.ticks(4000)
    assert len(indices) == g378_sample.TICKS
    assert indices[0] > 0 and indices[-1] < 4000
    gaps = {indices[i + 1] - indices[i] for i in range(len(indices) - 1)}
    assert len(gaps) == 1
    assert g378_sample.ticks(5) == []


def test_development_holdout_is_disjoint_from_the_evaluation_pool():
    buckets = {name: [] for name in ("a", "b", "c", "d", "e", "f")}
    pool, development = g378_sample.split_games(buckets)
    assert len(development) == g378_sample.DEVELOPMENT_HOLDOUT
    assert not set(pool) & set(development)
    assert sorted(pool + development) == sorted(buckets)


@pytest.mark.skipif(not PREREG.exists(), reason="prereg not present in this checkout")
def test_the_prereg_seal_holds():
    assert g334_seal.verify_seal(PREREG)
    assert g334_seal.scan_text(PREREG.read_text(encoding="utf-8")) == []
