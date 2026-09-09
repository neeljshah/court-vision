"""G365 attempt 2: candidate B's sealed properties, on synthetic fixtures only.

No broadcast frame is opened here and no sealed sweep number is produced: every draw uses the
`G365B-TEST` seed namespace, disjoint from attempt 1's `G365` and attempt 2's `G365B`, so a number
printed by a failing assertion below can never be mistaken for a row result.

The properties the amendment names: re-association gathers ONLY points inside the sealed band; a
refused, grossly-off initialisation is flagged INIT_FAIL and never enters the bar-1 / bar-4 judgment;
a noisy case improves; an exact input stays exact; the held-out strokes never enter the residual
(contract B8); no constant and no bar has moved (Q3); and the amendment seal holds (Q1).
"""
from pathlib import Path

import numpy as np

from scripts.platformkit.tracking import g362_fit_validate as fv
from scripts.platformkit.tracking import g362_strokes as st
from scripts.platformkit.tracking import g362_synth as synth
from scripts.platformkit.tracking import g365_refine as rf
from scripts.platformkit.tracking import g365_refine_b as rb
from scripts.platformkit.tracking import g365_sweep as sw
from scripts.platformkit.tracking import g365_sweep_b as sb
from scripts.platformkit.tracking.g334_court_template import HALF_COURT_QUAD
from scripts.platformkit.tracking.g334_seal import SEAL_PREFIX, seal_hex

EVID = (Path(__file__).resolve().parents[2] / "docs" / "evidence" / "tracking"
        / "g365_fitter_refinement_2026-09-09")
PREREG_ATT2 = EVID / "g365_prereg_att2_2026-09-09.md"
TEST_PREFIX = "G365B-TEST"
EXACT_PX = 1e-6


def _truth(index: int = 0) -> np.ndarray:
    return sw.geometry_matrix(sw.GEOMETRIES[index][1])


def _exact_supports(truth: np.ndarray, per_line: int = 25):
    """Points on the exact image of every straight marking, with their parent line's pixel length."""
    lines = rf.straight_template_lines()
    points, lengths = [], []
    for start, end in lines:
        pair = rf.apply_h(truth, np.vstack((start, end)))
        run = pair[0] + (pair[1] - pair[0]) * np.linspace(0.0, 1.0, per_line)[:, None]
        points.append(run)
        lengths.append(np.full(len(run), float(np.linalg.norm(pair[1] - pair[0]))))
    return np.concatenate(points, axis=0), np.concatenate(lengths)


def test_re_association_gathers_only_points_inside_the_sealed_band():
    """The band is what expels the foreign supports the G3_TIGHT diagnostic named."""
    truth = _truth()
    lines = rf.straight_template_lines()
    supports, _lengths = _exact_supports(truth)
    starts = np.asarray([line[0] for line in lines], dtype=float)
    ends = np.asarray([line[1] for line in lines], dtype=float)
    coef = rf.line_coefficients(rf.apply_h(truth, starts), rf.apply_h(truth, ends))
    home = rb.gather(truth, supports, lines)
    assert (home >= 0).all(), "every exact support starts on a marking"
    picked = np.zeros(len(supports), dtype=bool)
    picked[::7] = True
    # Displace along the ASSIGNED line's NORMAL: a shift along the line itself moves nothing, which
    # is why a plain vertical nudge leaves a support sitting on the near-vertical sidelines.
    displaced = supports.copy()
    displaced[picked] = displaced[picked] + coef[home[picked]][:, :2] * 9.0
    index = rb.gather(truth, displaced, lines)
    assert (index[picked] != home[picked]).all(), "9 px off a marking must leave that marking's band"
    assert int((index[picked] == -1).sum()) > int(picked.sum()) // 2, index[picked]
    kept = index >= 0
    assert kept.sum() >= rf.MIN_ASSIGNED, int(kept.sum())
    chosen = coef[index[kept]]
    distance = np.abs((displaced[kept] * chosen[:, :2]).sum(axis=1) + chosen[:, 2])
    assert float(distance.max()) <= rb.BAND_B_PX, float(distance.max())
    # The band is strictly narrower than candidate A's assignment radius: that is the change.
    assert rb.BAND_B_PX < rf.ASSIGN_MAX_PX


def test_the_straight_markings_are_exactly_invariant_under_the_court_mirror():
    """Why G2_WIDE's initialisation is a different basin and not a fit error (amendment section 1)."""
    lines = rf.straight_template_lines()

    def key(a, b):
        return tuple(sorted((tuple(np.round(a, 4)), tuple(np.round(b, 4)))))

    original = {key(pair[0], pair[1]) for pair in lines}
    mirrored = {key(np.array([50.0 - pair[0][0], pair[0][1]]),
                    np.array([50.0 - pair[1][0], pair[1][1]])) for pair in lines}
    assert original == mirrored, sorted(original ^ mirrored)


def test_a_refused_gross_initialisation_is_init_fail_and_leaves_the_bar_judgment():
    """The carve-out fires on BOTH clauses only, and never on an ordinary near-bar miss."""
    assert rb.init_fail("REFUSED", 469.2083)
    assert not rb.init_fail("REFUSED", 2.0160), "an ordinary REFUSED near-bar miss is not INIT_FAIL"
    assert not rb.init_fail("REFUSED", 1.8003)
    assert not rb.init_fail("VALID", 469.2083), "clause (i) is required too"
    assert not rb.init_fail("REFUSED", float("nan"))
    assert rb.INIT_FAIL_PX == 50.0 and rb.INIT_FAIL_STATE == "REFUSED"


def test_the_bar_clauses_evaluate_all_four_geometries_the_carveout_is_not_applied(tmp_path):
    """Fix 1d: the sealed carve-out is not applied to any bar; a flagged geometry keeps its row
    and its numbers, and a worsening INIT_FAIL geometry now fails both renamed bar clauses."""
    names = [name for name, _quad in sw.GEOMETRIES]
    recovery = []
    for name in names:
        flag = int(name == "G2_WIDE")
        base, gap = (469.2083, 469.3300) if flag else (1.8003, 0.6000)
        recovery.append([name, "INIT_FAIL" if flag else "REFUSED", flag, "%.4f" % base,
                         "%.4f" % gap, "%.4f" % gap, "%.4f" % (base - gap), "%.4f" % (base - gap),
                         sw.BAR_PX, 40, 30, 10, 900, 700, 3, 12, "ok",
                         "1.0", "1.0", "1.0", "1.0"])
    medians = {"%s|%.2f" % (name, sigma): {"baseline_median_px": 0.5, "a_median_px": 0.4,
                                           "b_median_px": 0.0 if sigma == 0.0 else 0.4,
                                           "b_improvement_median_px": 0.1, "draws": sb.DRAWS_B}
               for name in names for sigma in sw.SIGMAS}
    cached = {name: {"baseline_gap_px": 1.8003} for name in names}
    sb._summary(tmp_path, cached, recovery, medians)
    payload = __import__("json").loads((tmp_path / "summary_b.json").read_text(encoding="ascii"))
    assert payload["init_fail"] == ["G2_WIDE"]
    assert set(payload["recovery"]) == set(names), "the flagged geometry keeps its row"
    assert payload["recovery"]["G2_WIDE"]["b_gap_px"] == 469.33
    assert payload["bar"]["b_within_bar_all_four"] is False, "G2_WIDE (469.33 px) misses the bar"
    assert payload["bar"]["no_geometry_worsens"] is False, "G2_WIDE worsens 469.2083 -> 469.3300"
    assert payload["bar"]["sigma_050_median_within_bar"] is True
    assert payload["bar"]["exact_stays_zero"] is True


def test_a_non_init_fail_geometry_that_misses_the_bar_still_fails_bar_one(tmp_path):
    """The carve-out cannot be widened by accident: an ordinary REFUSED miss still fails."""
    names = [name for name, _quad in sw.GEOMETRIES]
    recovery = [[name, "REFUSED", 0, "2.0160", "2.1991", "2.1991", "-0.1831", "-0.1831",
                 sw.BAR_PX, 40, 30, 10, 900, 700, 3, 12, "ok", "1.0", "1.0", "1.0", "1.0"]
                for name in names]
    medians = {"%s|%.2f" % (name, sigma): {"baseline_median_px": 0.5, "a_median_px": 0.4,
                                           "b_median_px": 0.0 if sigma == 0.0 else 0.4,
                                           "b_improvement_median_px": 0.1, "draws": sb.DRAWS_B}
               for name in names for sigma in sw.SIGMAS}
    sb._summary(tmp_path, {name: {"baseline_gap_px": 2.016} for name in names}, recovery, medians)
    payload = __import__("json").loads((tmp_path / "summary_b.json").read_text(encoding="ascii"))
    assert payload["init_fail"] == []
    assert payload["bar"]["b_within_bar_all_four"] is False
    assert payload["bar"]["no_geometry_worsens"] is False


def test_exact_lines_stay_exact_before_and_after_candidate_b():
    """The control that keeps the refinement honest: an already-exact matrix must not move."""
    truth = _truth()
    row, base_gap, a_gap, b_gap = sb.one_draw(truth, "EXACT", 0.0, 0, prefix=TEST_PREFIX)
    assert base_gap < EXACT_PX, base_gap
    assert b_gap < EXACT_PX, b_gap
    assert a_gap < EXACT_PX, a_gap
    assert row[13] == "ok", row


def test_a_noisy_synthetic_case_improves_on_the_four_corner_baseline():
    """Sub-pixel endpoint noise: candidate B's median gap is below the 4-corner median."""
    truth = _truth()
    baseline, refined = [], []
    for draw in range(12):
        _row, base_gap, _a_gap, b_gap = sb.one_draw(truth, "NOISY", 1.0, draw, prefix=TEST_PREFIX)
        assert np.isfinite(base_gap) and np.isfinite(b_gap)
        baseline.append(base_gap)
        refined.append(b_gap)
    assert float(np.median(refined)) < float(np.median(baseline)), (baseline, refined)
    improved = sum(1 for b, r in zip(baseline, refined) if r < b)
    assert improved > len(baseline) // 2, (improved, baseline, refined)


def test_the_validation_strokes_are_untouched_and_never_enter_the_residual():
    """Contract B8, re-proved for candidate B: putting the held-out points in moves the answer."""
    truth = _truth()
    starts, ends = sw.draw_lines(truth, 0.5, sw.seed_of("HELDOUT", 0.5, 0, TEST_PREFIX))
    fit = np.concatenate([sw.supports_along(starts[i], ends[i]) for i in sw.FIT_LINES], axis=0)
    held = np.concatenate([sw.supports_along(starts[i], ends[i]) for i in sw.VAL_LINES], axis=0)
    before_fit, before_held = fit.tobytes(), held.tobytes()
    baseline = sw.corner_solve(starts, ends)
    assert baseline is not None
    refined, stats = rb.refine_b(baseline, fit)
    assert fit.tobytes() == before_fit and held.tobytes() == before_held
    assert stats["status"] == "ok" and stats["n_supports"] == len(fit)
    assert not {row.tobytes() for row in held} & {row.tobytes() for row in fit}
    contaminated, _stats = rb.refine_b(baseline, np.concatenate((fit, held), axis=0))
    assert not np.allclose(refined, contaminated), "held-out supports do not change the answer"


def test_too_few_supports_inside_the_band_return_the_starting_matrix_unchanged():
    """Missing support is not bad support: candidate B declines and says so (contract B3)."""
    truth = _truth()
    start, stats = rb.refine_b(truth, np.zeros((0, 2), dtype=float))
    assert stats["status"] == "too_few_assigned" and not stats["refined"]
    assert np.array_equal(start, truth / truth[2, 2])
    assert stats["rounds_run"] == 0


def test_the_rounds_converge_and_are_recorded():
    """Rounds are bounded by ROUNDS_B and stop early on the sealed corner tolerance."""
    truth = _truth()
    supports, lengths = _exact_supports(truth)
    nudged = truth.copy()
    nudged[0, 2] += 2.0
    _refined, stats = rb.refine_b(nudged, supports, lengths)
    assert 1 <= stats["rounds_run"] <= rb.ROUNDS_B, stats
    assert len(stats["shift_per_round"]) == stats["rounds_run"]
    assert len(stats["kept_per_round"]) >= stats["rounds_run"]
    if stats["rounds_run"] < rb.ROUNDS_B:
        assert stats["shift_per_round"][-1] <= rb.CONV_B_PX, stats


def test_the_length_weights_are_normalised_and_clipped():
    """A very long marking cannot buy an unbounded share of the objective."""
    keep = np.ones(4, dtype=bool)
    weights = rb.round_weights(np.array([1.0, 10.0, 100.0, 1000.0]), keep)
    assert float(weights.min()) >= rb.WEIGHT_CLIP[0] and float(weights.max()) <= rb.WEIGHT_CLIP[1]
    assert np.allclose(rb.round_weights(np.array([5.0, 5.0, 5.0, 5.0]), keep), 1.0)
    assert np.allclose(rb.round_weights(np.zeros(4), keep), 1.0)
    assert np.allclose(rb.round_weights(np.full(4, np.nan), keep), 1.0)


def test_no_bar_moved_and_the_sealed_constants_are_the_ones_the_amendment_names():
    """Q3: attempt 1's bars and spacings are read, never rewritten, and this fails if one drifts."""
    assert sw.BAR_PX == 1.0
    assert fv.MAX_MEDIAN_PX == 8.0 and fv.PENALTY_PX == 64.0
    assert st.SUPPORT_SPACING_PX == 6.0 and st.VALIDATION_DIVISOR == 4
    assert rf.HUBER_DELTA_PX == 2.0 and rf.MAX_ITER == 200 and rf.TOL == 1e-10
    assert rf.ASSIGN_MAX_PX == 12.0 and rf.MIN_ASSIGNED == 12
    assert rb.HUBER_DELTA_B_PX == 1.0 and rb.BAND_B_PX == 6.0 and rb.ROUNDS_B == 3
    assert rb.CONV_B_PX == 0.01 and rb.WEIGHT_CLIP == (0.5, 2.0)
    assert sw.SIGMAS == (0.0, 0.25, 0.5, 1.0) and sb.DRAWS_B == 40 and sb.DRAWS_B >= 30
    assert sb.PREFIX_B == "G365B" and sb.PREFIX_B != TEST_PREFIX


def test_the_attempt_two_seeds_are_disjoint_from_attempt_ones():
    """No attempt-2 draw can be an attempt-1 draw, and neither can be a test draw."""
    for sigma in sw.SIGMAS:
        a = sw.seed_of("G1_SYNTH_QUAD", sigma, 3)
        b = sw.seed_of("G1_SYNTH_QUAD", sigma, 3, sb.PREFIX_B)
        t = sw.seed_of("G1_SYNTH_QUAD", sigma, 3, TEST_PREFIX)
        assert len({a, b, t}) == 3, (sigma, a, b, t)
    assert sw.seed_of("G2_WIDE", 0.5, 7, sb.PREFIX_B) == sw.seed_of("G2_WIDE", 0.5, 7, sb.PREFIX_B)


def test_candidate_a_is_imported_not_copied():
    """Candidate A stays the code it was measured as; B reuses its residual by reference."""
    assert rb._weighted_residuals.__module__ == "scripts.platformkit.tracking.g365_refine_b"
    assert rb.rf is rf and rb.rf._residuals is rf._residuals
    unit = np.ones(3, dtype=float)
    assert np.array_equal(rb.round_weights(unit, np.ones(3, dtype=bool)), unit)


def test_amendment_prereg_seal_holds_over_lf_normalised_bytes_above_the_seal_line():
    """Q1: the amendment seal covers its LF-normalised body and predates every attempt-2 number."""
    assert PREREG_ATT2.exists(), PREREG_ATT2.as_posix()
    text = PREREG_ATT2.read_text(encoding="utf-8").replace("\r\n", "\n")
    lines = [line for line in text.split("\n") if line != ""]
    assert lines[-1].startswith(SEAL_PREFIX), lines[-1]
    assert lines[-1][len(SEAL_PREFIX):].strip() == seal_hex(text)
    assert len(text.split("\n")) - 1 <= 120, "the amendment stays inside its 120-line cap"


def test_the_geometry_path_supplies_one_parent_length_per_support():
    """The length weight is a property of the stroke, so its array must align with the supports."""
    truth = _truth()
    frame, _scale = fv.to_base_height(synth.render_court(truth))
    fit_strokes, _val = st.partition(st.extract_strokes(frame))
    lengths = sb.support_lengths(fit_strokes)
    assert len(lengths) == len(st.support_array(fit_strokes)), (len(lengths), len(fit_strokes))
    assert float(lengths.min()) >= st.MIN_STROKE_PX
    assert np.array_equal(sb.support_lengths([]), np.zeros(0, dtype=float))
