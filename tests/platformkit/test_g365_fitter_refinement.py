"""G365: the refinement's sealed properties, on synthetic fixtures only.

No broadcast frame is opened here and no sealed sweep number is produced: every draw in this file
uses the TEST seed namespace, which the sweep's sealed namespace can never collide with, so a number
printed by a failing assertion below can never be mistaken for a row result.

The four properties the spec names: an exact input recovers the known homography before AND after
the refinement; a noisy case improves; the VALIDATION strokes are untouched by the refinement and
never enter its residual (contract B8); and the iteration cap is honoured. The seal check and the
unmoved-bar tripwire (Q1, Q3) are here for the same reason they are in G362's test -- they fail
loudly if someone edits the preregistration or a bar after the fact.
"""
from pathlib import Path

import numpy as np

from scripts.platformkit.tracking import g362_fit_validate as fv
from scripts.platformkit.tracking import g362_strokes as st
from scripts.platformkit.tracking import g362_synth as synth
from scripts.platformkit.tracking import g365_refine as rf
from scripts.platformkit.tracking import g365_sweep as sw
from scripts.platformkit.tracking.g334_court_template import TEMPLATE_POINTS
from scripts.platformkit.tracking.g334_seal import SEAL_PREFIX, seal_hex

PREREG = (Path(__file__).resolve().parents[2] / "docs" / "evidence" / "tracking"
          / "g365_fitter_refinement_2026-09-09" / "g365_prereg_2026-09-09.md")
TEST_PREFIX = "G365-TEST"
EXACT_PX = 1e-6


def _truth(index: int = 0) -> np.ndarray:
    return sw.geometry_matrix(sw.GEOMETRIES[index][1])


def test_the_nine_straight_markings_are_what_the_residual_is_defined_against():
    """The arcs are excluded on purpose: a point-to-LINE residual needs a straight marking."""
    lines = rf.straight_template_lines()
    assert len(lines) == 9, len(lines)
    assert all(len(pair) == 2 and pair[0].shape == (2,) for pair in lines)
    assert set(sw.FIT_LINES) | set(sw.VAL_LINES) == set(range(9))
    assert not set(sw.FIT_LINES) & set(sw.VAL_LINES)


def test_exact_lines_recover_the_known_homography_before_and_after_the_refinement():
    """G362's diagnostic, carried forward: the corner solve is exact on exact lines, and stays so.

    This is the control that keeps the refinement honest. A refinement that moved an already-exact
    homography would be fitting its own residual convention rather than the markings.
    """
    truth = _truth()
    row, base_gap, ref_gap = sw.one_draw(truth, "EXACT", 0.0, 0, prefix=TEST_PREFIX)
    assert base_gap < EXACT_PX, base_gap
    assert ref_gap < EXACT_PX, ref_gap
    assert row[10] == "ok", row


def test_a_noisy_synthetic_case_improves_on_the_four_corner_baseline():
    """Sub-pixel endpoint noise: the refined gap is below the 4-corner gap on the same draw."""
    truth = _truth()
    baseline, refined = [], []
    for draw in range(12):
        _row, base_gap, ref_gap = sw.one_draw(truth, "NOISY", 1.0, draw, prefix=TEST_PREFIX)
        assert np.isfinite(base_gap) and np.isfinite(ref_gap)
        baseline.append(base_gap)
        refined.append(ref_gap)
    assert float(np.median(refined)) < float(np.median(baseline)), (baseline, refined)
    # The claim is about the MEDIAN, which is what the row's bar is stated over; per draw the
    # property is only that a strict majority improve, and a draw that worsens is not a defect.
    improved = sum(1 for b, r in zip(baseline, refined) if r < b)
    assert improved > len(baseline) // 2, (improved, baseline, refined)


def test_the_validation_lines_are_untouched_and_never_enter_the_residual():
    """Contract B8: the held-out supports are byte-identical across the refinement and unread."""
    truth = _truth()
    starts, ends = sw.draw_lines(truth, 0.5, sw.seed_of("HELDOUT", 0.5, 0, TEST_PREFIX))
    fit = np.concatenate([sw.supports_along(starts[i], ends[i]) for i in sw.FIT_LINES], axis=0)
    held = np.concatenate([sw.supports_along(starts[i], ends[i]) for i in sw.VAL_LINES], axis=0)
    before_fit, before_held = fit.tobytes(), held.tobytes()
    baseline = sw.corner_solve(starts, ends)
    assert baseline is not None
    refined, stats = rf.refine_homography(baseline, fit)
    assert fit.tobytes() == before_fit and held.tobytes() == before_held
    assert stats["n_supports"] == len(fit) and stats["n_assigned"] <= len(fit)
    assert not {row.tobytes() for row in held} & {row.tobytes() for row in fit}
    # The proof that the held-out points are absent from the residual: putting them IN moves the
    # answer. If they were already being read, this second call would return the same matrix.
    contaminated, _stats = rf.refine_homography(baseline, np.concatenate((fit, held), axis=0))
    assert stats["status"] == "ok"
    assert not np.allclose(refined, contaminated), "held-out supports do not change the answer"


def test_the_iteration_cap_is_honoured():
    """A sealed cap that the solver may not exceed, whatever the residual is doing."""
    truth = _truth()
    starts, ends = sw.draw_lines(truth, 1.0, sw.seed_of("CAP", 1.0, 0, TEST_PREFIX))
    fit = np.concatenate([sw.supports_along(starts[i], ends[i]) for i in sw.FIT_LINES], axis=0)
    baseline = sw.corner_solve(starts, ends)
    _refined, stats = rf.refine_homography(baseline, fit, max_iter=3)
    assert stats["n_fev"] <= 3, stats
    assert stats["max_iter"] == 3


def test_too_few_assigned_supports_return_the_starting_matrix_unchanged():
    """Missing support is not bad support: the refinement declines and says so (contract B3)."""
    truth = _truth()
    start, stats = rf.refine_homography(truth, np.zeros((0, 2), dtype=float))
    assert stats["status"] == "too_few_assigned" and not stats["refined"]
    assert np.array_equal(start, truth / truth[2, 2])


def test_the_four_sealed_geometries_paint_and_detect_whole_strokes():
    """Fixture viability only: no recovery gap is computed here, and none is recorded anywhere."""
    for name, quad in sw.GEOMETRIES:
        matrix = sw.geometry_matrix(quad)
        frame, scale = fv.to_base_height(synth.render_court(matrix))
        assert scale == 1.0 and frame.shape[:2] == synth.SYNTH_SHAPE
        strokes = st.extract_strokes(frame)
        assert len(strokes) >= fv.MIN_STROKES, (name, len(strokes))
        fit_strokes, val_strokes = st.partition(strokes)
        assert len(st.families_of(val_strokes)) >= fv.MIN_VAL_FAMILIES, name
        assert len(st.support_array(val_strokes)) >= fv.MIN_VAL_POINTS, name
        assert not ({s.stroke_id for s in fit_strokes} & {s.stroke_id for s in val_strokes}), name


def test_no_bar_moved_and_the_sealed_constants_are_the_ones_the_prereg_names():
    """Q3: G362's bars and spacings are read, never rewritten, and this fails if one drifts."""
    assert sw.BAR_PX == 1.0
    assert fv.MAX_MEDIAN_PX == 8.0 and fv.PENALTY_PX == 64.0
    assert fv.MIN_VAL_POINTS == 30 and fv.MIN_VAL_FAMILIES == 2
    assert st.SUPPORT_SPACING_PX == 6.0 and st.VALIDATION_DIVISOR == 4
    assert rf.HUBER_DELTA_PX == 2.0 and rf.MAX_ITER == 200 and rf.TOL == 1e-10
    assert rf.ASSIGN_MAX_PX == 12.0 and rf.MIN_ASSIGNED == 12
    assert sw.SIGMAS == (0.0, 0.25, 0.5, 1.0) and sw.DRAWS == 40


def test_the_sweep_seeds_are_content_addressed_and_reproduce():
    """Determinism: a draw is a pure function of its name, sigma and index, and of nothing else."""
    assert sw.seed_of("G1_SYNTH_QUAD", 0.5, 7) == sw.seed_of("G1_SYNTH_QUAD", 0.5, 7)
    assert sw.seed_of("G1_SYNTH_QUAD", 0.5, 7) != sw.seed_of("G1_SYNTH_QUAD", 0.5, 8)
    assert sw.seed_of("G1_SYNTH_QUAD", 0.5, 7, TEST_PREFIX) != sw.seed_of("G1_SYNTH_QUAD", 0.5, 7)
    truth = _truth()
    first = sw.draw_lines(truth, 0.5, sw.seed_of("R", 0.5, 0, TEST_PREFIX))
    second = sw.draw_lines(truth, 0.5, sw.seed_of("R", 0.5, 0, TEST_PREFIX))
    assert np.array_equal(first[0], second[0]) and np.array_equal(first[1], second[1])


def test_the_reprojection_gap_is_g362s_own_quantity():
    """The metric is G362's, unchanged: the median over the whole 398-point template."""
    truth = _truth()
    assert len(TEMPLATE_POINTS) == 398
    assert synth.reprojection_median(truth, truth, TEMPLATE_POINTS) == 0.0
    translate = np.array([[1.0, 0.0, 5.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    shifted = translate @ truth
    assert abs(synth.reprojection_median(truth, shifted, TEMPLATE_POINTS) - 5.0) < 1e-4


def test_prereg_seal_holds_over_lf_normalised_bytes_above_the_seal_line():
    """Q1: the seal covers the LF-normalised body and predates every number in the row."""
    assert PREREG.exists(), PREREG.as_posix()
    text = PREREG.read_text(encoding="utf-8").replace("\r\n", "\n")
    lines = [line for line in text.split("\n") if line != ""]
    assert lines[-1].startswith(SEAL_PREFIX), lines[-1]
    assert lines[-1][len(SEAL_PREFIX):].strip() == seal_hex(text)
