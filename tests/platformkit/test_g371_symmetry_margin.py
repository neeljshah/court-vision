"""G371 prepare-time checks for the truth-free symmetry class selector."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from scripts.platformkit.tracking import g334_seal
from scripts.platformkit.tracking import g362_fit_validate as fv
from scripts.platformkit.tracking import g362_synth as synth
from scripts.platformkit.tracking import g365_sweep as sweep
from scripts.platformkit.tracking import g371_run as run
from scripts.platformkit.tracking import g371_symmetry_margin as margin
from scripts.platformkit.tracking.g367_search import _candidates
from scripts.platformkit.tracking.g367_symmetry import GROUP, compose, equivalent, recovery_modulo_symmetry
from scripts.platformkit.tracking.g334_court_template import TEMPLATE_POINTS


ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / "docs/evidence/tracking/g371_symmetry_margin_2026-09-09/g371_prereg_2026-09-09.md"


def _candidate(matrix: np.ndarray, objective: float, rank: int) -> margin.ScoredCandidate:
    return margin.ScoredCandidate(matrix, objective, "identity", rank)


def test_truth_swap_leaves_selection_identical() -> None:
    base = synth.known_matrix()
    other = base.copy()
    other[0, 2] += 30.0
    items = [_candidate(base, 1.0, 1), _candidate(other, 0.8, 2)]
    first = margin.select_from_scored(items)
    swapped_truth = compose(base, GROUP[1])
    second = margin.select_from_scored(items)
    assert recovery_modulo_symmetry(swapped_truth, base, TEMPLATE_POINTS)["modulo_gap_px"] >= 0.0
    assert (first.geometry_status, first.margin, first.winner.objective) == (
        second.geometry_status, second.margin, second.winner.objective)


def test_cloned_candidates_leave_margin_unchanged() -> None:
    base = synth.known_matrix()
    other = base.copy()
    other[1, 2] += 30.0
    original = [_candidate(base, 1.0, 1), _candidate(other, 0.8, 2)]
    cloned = original + [_candidate(base.copy(), 1.0, 99), _candidate(other.copy(), 0.8, 100)]
    assert margin.select_from_scored(original).margin == margin.select_from_scored(cloned).margin


def test_planted_distinct_class_inside_band_is_refused() -> None:
    base = synth.known_matrix()
    planted = base.copy()
    planted[0, 2] += 30.0
    outcome = margin.select_from_scored([_candidate(base, 1.0, 1), _candidate(planted, 0.99, 2)])
    assert outcome.geometry_status == "REFUSED_MARGIN"
    assert outcome.margin is not None and outcome.margin < margin.ACCEPT_MARGIN


def test_exact_control_is_zero() -> None:
    assert margin.exact_modulo_gap(synth.known_matrix()) == 0.0


def test_imported_g367_entry_points_smoke_one_geometry() -> None:
    truth = sweep.geometry_matrix(sweep.GEOMETRIES[0][1])
    frame, _scale = fv.to_base_height(synth.render_court(truth))
    ranked, hypotheses, images, _fit, _field = _candidates(frame)
    assert ranked and hypotheses > 0 and images > 0
    candidate = compose(ranked[0][2], GROUP[0])
    assert equivalent(candidate, ranked[0][2], TEMPLATE_POINTS, margin.SYM_EQ_PX)
    result = recovery_modulo_symmetry(truth, candidate, TEMPLATE_POINTS)
    assert result["modulo_gap_px"] >= 0.0


def test_prereg_seal_holds() -> None:
    assert g334_seal.verify_seal(PREREG)


def test_probe_error_is_zero_against_the_truth_itself() -> None:
    truth = run.truth_of("G1_SYNTH_QUAD")
    error, index = run.probe_errors(truth, truth, synth.SYNTH_SHAPE)
    # 1e-5 m is the float32 floor of cv2.perspectiveTransform, not a tolerance on the fit.
    assert len(index) >= 30 and float(np.max(error)) < 1e-5


def test_seed_is_content_addressed_and_draw_specific() -> None:
    first = run.seed_of("G1_SYNTH_QUAD", 0.25, 0)
    assert first == run.seed_of("G1_SYNTH_QUAD", 0.25, 0)
    assert first != run.seed_of("G1_SYNTH_QUAD", 0.25, 1)
    assert first != run.seed_of("G2_WIDE", 0.25, 0)


def test_noisy_frame_keeps_the_clean_painter_and_moves_the_lines() -> None:
    truth = run.truth_of("G1_SYNTH_QUAD")
    clean, noisy = run.clean_frame(truth), run.noisy_frame(truth, 1.0, run.seed_of("G1_SYNTH_QUAD", 1.0, 0))
    assert clean.shape == noisy.shape and clean.dtype == noisy.dtype
    assert not np.array_equal(clean, noisy)
