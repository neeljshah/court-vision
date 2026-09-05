"""G294 reproduction, complete eligibility, overlap and descriptive regression."""

import math

import pytest

from scripts.platformkit.tracking.g294_gap_conditioned_implausibility import (
    BUCKETS, analyze, gap_bucket, loglog_fit, read_steps, report, reproduce,
)


def test_committed_reproduction_exhaustive_buckets_and_overlap():
    rows, source = read_steps()
    result = analyze(rows)
    checks = result["reproduction"]
    assert checks["baseline"] == {"numerator": 4090, "denominator": 29973, "rate": 4090 / 29973}
    assert f"{checks['baseline']['rate']:.6f}" == "0.136456"
    assert checks["gap1_rate"] == {"numerator": 2961, "denominator": 26523, "rate": 2961 / 26523}
    assert f"{checks['gap1_rate']['rate']:.4f}" == "0.1116"
    assert checks["gap_above1_rate"]["rate"] == 1129 / 3450
    assert checks["gap_above1_share_all"]["rate"] == 3450 / 29973
    assert checks["gap_above1_share_implausible"]["rate"] == 1129 / 4090
    table = result["per_gap"]
    assert tuple(c["gap_bucket"] for c in table) == BUCKETS
    assert [c["eligible_steps_at_gap"] for c in table] == [26523, 1413, 616, 383, 219, 504, 315]
    assert [c["implausible_steps"] for c in table] == [2961, 448, 228, 157, 67, 177, 52]
    assert sum(c["eligible_steps_at_gap"] for c in table) == len(rows) == 29973
    assert sum(c["implausible_steps"] for c in table) == 4090
    # Independently define the disjoint intervals, including the open-ended tail.
    assigned = []
    for lower, upper in [(1, 1), (2, 2), (3, 3), (4, 4), (5, 5), (6, 10), (11, math.inf)]:
        assigned.extend(r["step_index"] for r in rows if lower <= r["frame_gap"] <= upper)
    assert len(assigned) == len(set(assigned)) == 29973
    assert set(assigned) == {r["step_index"] for r in rows}
    assert result["standardized_rate"] == 2961 / 26523
    assert result["gap_composition_share"] == (4090 / 29973 - 2961 / 26523) / (4090 / 29973)
    assert result["overlap_implausible_steps"] == {
        "gap1_small_image": 623, "gap1_larger_image": 2338,
        "gap_above1_small_image": 7, "gap_above1_larger_image": 1122,
    }
    assert source["bytes"] > 0
    assert result["historical_bimodal_overlap"] is None
    assert all(c["small_cell"] == "OK (>=30 steps)" for c in table)
    assert report(result).isascii()


def test_gap_boundaries_and_invalid_gaps():
    assert [gap_bucket(g) for g in [1, 2, 3, 4, 5, 6, 10, 11, 30, 1000]] == [
        "1", "2", "3", "4", "5", "6-10", "6-10", "above 10", "above 10", "above 10"]
    for invalid in (0, -1, 1.5, True):
        with pytest.raises(ValueError, match="positive integer"):
            gap_bucket(invalid)


def test_scaling_recovers_models_and_residual_standard_error():
    gaps = [1.0, 2.0, 3.0, 4.0, 5.0, 7.0, 16.0]
    for exponent in (0.0, 1.0, 1.5):
        fit = loglog_fit(gaps, [2 * g ** exponent for g in gaps])
        assert fit["exponent"] == pytest.approx(exponent, abs=1e-12)
        assert fit["standard_error"] == pytest.approx(0, abs=1e-12)
    # For x=(0,1,2,3), y=(0,1,1,3): slope=.9, Sxx=5, SSE=.7, df=2.
    fit = loglog_fit([math.exp(x) for x in (0, 1, 2, 3)],
                     [math.exp(y) for y in (0, 1, 1, 3)])
    assert fit["exponent"] == pytest.approx(0.9)
    assert fit["standard_error"] == pytest.approx(math.sqrt(0.7 / 2 / 5))
    assert "p_value" not in fit
    with pytest.raises(ValueError, match="positive finite"):
        loglog_fit([1, 2, 3], [1, 0, 3])


def test_reproduction_stops_before_analysis_on_mismatch():
    rows, _ = read_steps()
    with pytest.raises(ValueError, match="STOP"):
        reproduce(rows[:-1])
    altered = [dict(r) for r in rows]
    next(r for r in altered if r["frame_gap"] == 1)["frame_gap"] = 2
    with pytest.raises(ValueError, match="STOP"):
        analyze(altered)


def test_small_cell_is_marked_and_retained():
    rows, _ = read_steps()
    tail = [r for r in rows if r["frame_gap"] > 10]
    for row in tail[1:]:
        row["frame_gap"] = 2
    result = analyze(rows)
    cell = result["per_gap"][-1]
    assert cell["eligible_steps_at_gap"] == 1
    assert cell["small_cell"] == "TOO SMALL TO READ"
    assert result["loglog_fits"]["court_displacement_ft"]["median_cells"] == 7
    assert "TOO SMALL TO READ" in report(result)
