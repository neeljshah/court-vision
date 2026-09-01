"""Synthetic-shot proof for the football field-view gate.

Three shot types the real broadcast actually mixes -- a wide field view, a
studio graphic card, and a sideline crowd close-up -- plus a flat green card
that has turf colour but no structure. Thresholds were fixed here before any
real footage was scored.
"""
import numpy as np
import pytest

from scripts.platformkit.tracking.football_fieldview import (
    CUT_GUARD_FRAMES, MIN_SCENE_FRAMES, field_view_gate, scan, scene_bounds)
from scripts.platformkit.tracking.football_snap import detect_snaps

H, W, FPS = 180, 320, 30.0


def _noise(rng, base, spread, shape=(H, W, 3)):
    grain = rng.integers(-spread, spread + 1, size=shape)
    return np.clip(np.asarray(base, dtype=int) + grain, 0, 255).astype(np.uint8)


def _field(rng):
    """Wide field view: turf, near-parallel yard lines, small players."""
    frame = _noise(rng, (60, 150, 70), 6)
    for x in range(30, W, 45):
        slant = int((x - W / 2) * 0.06)  # perspective: near-parallel, not exact
        for y in range(H):
            column = min(W - 1, max(0, x + int(slant * y / H)))
            frame[y, column:column + 2] = (245, 245, 245)
    for cx, cy in rng.integers(20, 140, size=(11, 2)):
        frame[cy:cy + 12, cx:cx + 7] = (30, 30, 30)
    return frame


def _studio(rng):
    """Full-frame graphic card: flat navy with one title block. Almost no edges."""
    frame = np.zeros((H, W, 3), np.uint8)
    frame[:, :] = (110, 45, 25)
    frame[70:100, 60:260] = (230, 230, 230)
    return frame


def _crowd(rng):
    """Sideline close-up: textured, warm, no turf."""
    return _noise(rng, (40, 55, 100), 45)


def _flat_green(rng):
    """Turf colour with no structure -- the case only the edge test can reject."""
    frame = np.zeros((H, W, 3), np.uint8)
    frame[:, :] = (60, 150, 70)
    return frame


@pytest.mark.parametrize("maker,expected", [
    (_field, True), (_studio, False), (_crowd, False), (_flat_green, False)])
def test_raw_field_view_verdict_by_shot_type(maker, expected):
    rng = np.random.default_rng(5)
    table = scan([maker(rng) for _ in range(6)])
    assert bool(table["raw"].all()) is expected, table.iloc[0].to_dict()
    if expected:
        assert table["score"].min() > 0.5


def _sequence(blocks):
    rng = np.random.default_rng(9)
    return [maker(rng) for maker, count in blocks for _ in range(count)]


def test_cut_is_found_and_the_guard_band_is_closed():
    table = scan(_sequence([(_crowd, 60), (_field, 60)]))
    assert [span[0] for span in scene_bounds(table["cut_diff"].to_numpy())] == [0, 60]
    gate = field_view_gate(table)
    assert not gate[:60].any(), "crowd shot must never be accepted"
    assert not gate[60:60 + CUT_GUARD_FRAMES].any(), "guard band after the cut"
    assert not gate[120 - CUT_GUARD_FRAMES:].any(), "guard band before the end"
    assert gate[75:105].all()


def test_short_field_flash_is_rejected_by_the_hysteresis():
    flash = MIN_SCENE_FRAMES - 7
    table = scan(_sequence([(_crowd, 40), (_field, flash), (_crowd, 40)]))
    assert len(scene_bounds(table["cut_diff"].to_numpy())) == 3
    assert not field_view_gate(table).any()


def test_gate_drops_candidates_outside_the_mask():
    energy = [1.0] * 100 + [10.0] * 100 + [1.0] * 100 + [10.0] * 100
    ungated = detect_snaps(energy, FPS)
    assert [e["frame"] for e in ungated] == [96, 296]
    gate = np.ones(len(energy), dtype=bool)
    gate[90:150] = False
    assert [e["frame"] for e in detect_snaps(energy, FPS, gate=gate)] == [296]


def test_rows_declare_image_px_and_carry_the_gate():
    from scripts.platformkit.tracking.football_fieldview import _rows
    rng = np.random.default_rng(2)
    table = scan([_field(rng) for _ in range(4)])
    gate = np.array([False, True, True, False])
    rows = _rows(table, gate, FPS)
    assert set(rows["coordinate_space"]) == {"image_px"}
    assert set(rows["calibration"]) == {"none"}
    assert rows["is_field_view"].tolist() == [False, True, True, False]
    assert rows["x"].isna().all(), "a field-view verdict claims no location"
