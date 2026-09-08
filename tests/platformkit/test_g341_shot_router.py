"""Synthetic checks for G341's shot routing and floor propagation contracts."""

from __future__ import annotations

import hashlib
from pathlib import Path

import cv2
import numpy as np

from scripts.platformkit.tracking.floor_motion import (
    compose_chain,
    estimate_floor_motion,
    fit_and_score,
    propagate_frames,
)
from scripts.platformkit.tracking.shot_router import RouteRecord, route_frames, _seal_determinism


ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / "docs/evidence/tracking/g341_prereg_2026-09-08.md"


def _solid(value: int) -> np.ndarray:
    return np.full((180, 320, 3), value, dtype=np.uint8)


def _texture(seed: int = 1) -> np.ndarray:
    generator = np.random.default_rng(seed)
    image = generator.integers(0, 256, (180, 320), dtype=np.uint8)
    return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)


def test_cut_fires_at_stable_texture_switch_and_ignores_one_flash():
    stable, changed = _solid(20), _solid(210)
    routed, cuts = route_frames([stable] * 5 + [changed] * 6)
    assert cuts == [5]
    assert [record.shot_id for record in routed[:5]] == [0] * 5
    assert [record.shot_id for record in routed[5:]] == [1] * 6
    _, flash_cuts = route_frames([stable] * 3 + [_solid(220)] + [stable] * 5)
    assert flash_cuts == []


def test_floor_motion_recovers_known_planar_warp_and_composes_chain():
    source = _texture()
    matrix = np.array(((1.0, 0.0, 2.0), (0.0, 1.0, 1.0), (0.0, 0.0, 1.0)))
    target = cv2.warpPerspective(source, matrix, (320, 180), borderMode=cv2.BORDER_REFLECT)
    recovered, diagnostics = estimate_floor_motion(source, target)
    assert recovered is not None, diagnostics
    grid = np.float32(((30, 30), (160, 30), (290, 30), (30, 90), (160, 90), (290, 90), (30, 150), (160, 150), (290, 150))).reshape(1, -1, 2)
    error = np.linalg.norm(cv2.perspectiveTransform(grid, recovered) - cv2.perspectiveTransform(grid, matrix), axis=2)
    assert float(error.max()) < 0.5
    chained = compose_chain([matrix] * 5)
    assert np.allclose(chained, np.linalg.matrix_power(matrix, 5))


def test_p90_reflects_a_validation_only_perturbation_while_the_fit_does_not_move():
    """B1/B8 fix-1b: perturb only the held-out VALIDATION matches by a known 5 px
    offset. The FIT set (the other 3 of every 4 matches) is untouched, so the
    fitted homography must reproduce a FIT-only cv2.findHomography call exactly,
    and the FIT-derived diagnostics (inliers/share/hull) must not move -- only
    p90, scored on the perturbed validation points, must jump to ~5 px."""
    shape = (180, 320)
    grid = np.array([[x, y] for y in range(10, 170, 32) for x in range(10, 310, 40)], dtype=np.float32)
    matrix = np.array(((1.0, 0.02, 3.0), (0.0, 1.0, 2.0), (0.0002, 0.0, 1.0)))
    target = cv2.perspectiveTransform(grid.reshape(1, -1, 2), matrix)[0]
    baseline_matrix, baseline_diag = fit_and_score(grid, target, shape)
    assert baseline_matrix is not None, baseline_diag
    assert baseline_diag[0] == "accepted" and baseline_diag[4] < 0.01

    validation = np.arange(len(grid)) % 4 == 0
    direct_fit_matrix, _ = cv2.findHomography(grid[~validation], target[~validation], cv2.RANSAC, 3.0)
    assert np.allclose(baseline_matrix, direct_fit_matrix)

    perturbed = target.copy()
    perturbed[validation] += np.array([5.0, 0.0], dtype=np.float32)
    perturbed_matrix, perturbed_diag = fit_and_score(grid, perturbed, shape)
    assert perturbed_matrix is None and perturbed_diag[0] == "high_residual"
    assert perturbed_diag[1:4] == baseline_diag[1:4], "FIT-only diagnostics must not move"
    assert 4.9 < perturbed_diag[4] < 5.1, "p90 must reflect the 5 px validation-only offset"


def test_replayed_segment_is_flagged_by_dhash():
    segment = [_texture(seed) for seed in range(8)]
    records, _ = route_frames(segment + [_texture(99)] * 8 + segment)
    assert all(record.replay_flag == "REPLAY" for record in records[-8:])


def test_two_runs_are_byte_identical_after_sealing_determinism():
    """fix 1d: cv2's RANSAC (used in _static_inlier_fraction) draws from a
    process-global RNG that a prior section's calls could leave in a
    different state; reseal before each run and require two independent
    route_frames passes over the same textured construct to match exactly,
    including the RANSAC-derived static_inlier_fraction floats."""
    frames = [_texture(seed) for seed in range(6)] + [_texture(seed + 50) for seed in range(6)]
    _seal_determinism()
    first_records, first_cuts = route_frames(list(frames))
    _seal_determinism()
    second_records, second_cuts = route_frames(list(frames))
    assert first_cuts == second_cuts
    assert first_records == second_records


def test_empty_anchor_set_never_emits_direct():
    frames = [_texture(), _texture()]
    routes = [RouteRecord(index, 0, "UNKNOWN", "UNKNOWN", 0.0, 1.0, 0, 0.0, None) for index in range(2)]
    records = propagate_frames(frames, routes, anchors=set())
    assert all(record.state != "DIRECT" for record in records)


def test_propagation_never_carries_a_mapping_across_a_routed_cut():
    frames = [_texture(), _texture()]
    routes = [
        RouteRecord(0, 0, "UNKNOWN", "UNKNOWN", 0.0, 1.0, 0, 0.0, None),
        RouteRecord(1, 1, "UNKNOWN", "UNKNOWN", 0.0, 1.0, 0, 0.0, None),
    ]
    records = propagate_frames(frames, routes)
    assert [record for record in records if record.state != "ANCHOR"] == []


def test_preregistration_seal_uses_lf_normalized_prereg_file_bytes():
    text = PREREG.read_text(encoding="utf-8").replace("\r\n", "\n")
    prefix, seal = text.rsplit("\nSEAL sha256 ", 1)
    assert "\n" not in seal.strip()
    actual = hashlib.sha256((prefix + "\n").encode("utf-8")).hexdigest()
    assert actual == seal.strip()
