"""Focused construct coverage for the calibration evidence report (gap S05).

Per-file test only:
`python -m pytest scripts/platformkit/eval_gate/test_calibration_report.py -q`
"""
import numpy as np

from scripts.platformkit.calib_decomp import decompose
from scripts.platformkit.eval_gate.calibration_report import (
    PREREG_SEAL, _bin_table, _from_bins, build_report,
)
from scripts.platformkit.eval_gate.scoring import ece


def _flattening_records(n: int = 400) -> list[dict]:
    records = []
    for index in range(n):
        band = index % 10
        records.append({
            "event_id": "event-%03d" % index,
            "p_base": 0.05 + (0.1 * band),
            "y": float(band % 2 == 0),
        })
    return records


def test_flattened_isotonic_output_is_not_an_improvement() -> None:
    report = build_report(_flattening_records(), "synthetic", min_n=200)

    assert len(report["reliability_bins"]) == 10
    assert all("n" in row for row in report["reliability_bins"])
    for key in ("max_loser_wp", "ece_before", "ece_after", "murphy_before",
                "murphy_after", "sharpness_before", "sharpness_after",
                "prediction_column", "dropped_rows", "verdict"):
        assert key in report
    assert set(report["murphy_before"]) == {"reliability", "resolution", "uncertainty"}
    assert report["ece_after"] < report["ece_before"]
    assert report["murphy_after"]["resolution"] < report["murphy_before"]["resolution"]
    assert report["verdict"] == "FLATTENED"


def test_report_reproduces_its_own_summary_from_its_published_bins() -> None:
    """The attempt-1 defect (S42): bin table and summary must share one edge rule."""
    report = build_report(_flattening_records(), "synthetic", min_n=200)

    assert report["reproduction_max_abs_diff"] < 1e-9
    for table_key, ece_key, murphy_key in (
        ("reliability_bins", "ece_before", "murphy_before"),
        ("reliability_bins_after", "ece_after", "murphy_after"),
    ):
        redone = _from_bins(report[table_key], report["base_rate"], report["scored_rows"])
        assert abs(redone["ece"] - report[ece_key]) < 1e-9
        assert abs(redone["reliability"] - report[murphy_key]["reliability"]) < 1e-9
        assert abs(redone["resolution"] - report[murphy_key]["resolution"]) < 1e-9


def test_bin_table_matches_the_scoring_and_decompose_edge_rule() -> None:
    """Predictions ON the 0.1 grid are where the two old rules disagreed."""
    rng = np.random.default_rng(4242)
    probs = list(np.round(rng.uniform(0.0, 1.0, 500), 1))  # every value on the grid
    outcomes = list(rng.integers(0, 2, 500).astype(float))

    table = _bin_table(probs, outcomes, 10)
    assert len(table) == 10
    assert sum(row["n"] for row in table) == 500

    base_rate = float(np.mean(outcomes))
    redone = _from_bins(table, base_rate, 500)
    murphy = decompose(probs, outcomes, bins=10)
    assert abs(redone["ece"] - ece(probs, outcomes, bins=10)) < 1e-12
    assert abs(redone["reliability"] - murphy["reliability"]) < 1e-12
    assert abs(redone["resolution"] - murphy["resolution"]) < 1e-12


def test_below_min_n_is_insufficient_and_carries_no_metrics() -> None:
    report = build_report(_flattening_records(50), "synthetic", min_n=200)
    assert report["verdict"] == "INSUFFICIENT"
    assert report["scored_rows"] == 50 and report["shortfall"] == 150
    assert report["ece_before"] is None and report["murphy_before"] is None


def test_dropped_rows_are_counted_never_silently_removed() -> None:
    records = _flattening_records(300)
    records[0]["y"] = None            # non-binary outcome
    records[1]["p_base"] = float("nan")  # non-finite prediction
    report = build_report(records, "synthetic", min_n=200)
    assert report["input_rows"] == 300
    assert report["dropped_rows"] == 2
    assert report["scored_rows"] == 298


def test_every_report_names_its_prereg_and_seal() -> None:
    for report in (build_report(_flattening_records(), "synthetic", min_n=200),
                   build_report(_flattening_records(50), "synthetic", min_n=200)):
        assert report["prereg_path"].endswith("S05_calibration_prereg_2026-09-03.md")
        assert report["prereg_seal_sha256"] == PREREG_SEAL
        assert "np.linspace" in report["bin_edge_rule"]
        assert report["order_basis"] in ("POSITIONAL-ORDER", "event_date")
