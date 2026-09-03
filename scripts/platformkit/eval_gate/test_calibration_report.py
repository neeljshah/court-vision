"""Focused construct coverage for the calibration evidence report (gap S05).

Per-file test only:
`python -m pytest scripts/platformkit/eval_gate/test_calibration_report.py -q`
"""
import json
from pathlib import Path

import numpy as np
import pytest

from scripts.platformkit.calib_decomp import decompose
from scripts.platformkit.eval_gate.calibration_report import (
    PREREG_SEAL, _bin_table, _from_bins, build_report,
)
from scripts.platformkit.eval_gate import worktree_marker
from scripts.platformkit.eval_gate.scoring import ece

_REPO = Path(__file__).resolve().parents[3]


def _require_default_report_evidence(landed_path: Path, cache_path: Path) -> None:
    """S156: missing reproduction evidence skips only in a worktree checkout."""
    if landed_path.exists() and cache_path.exists():
        return
    missing = ", ".join(str(path) for path in (landed_path, cache_path) if not path.exists())
    if worktree_marker.is_worktree_checkout():
        pytest.skip(f"worktree checkout: reproduction evidence absent: {missing}")
    pytest.fail(f"main-repo checkout: reproduction evidence absent: {missing}")


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


# --------------------------------------------------------------------------- #
# S50: per-corpus_unit chronological walk (opt-in; default OFF)
# --------------------------------------------------------------------------- #

def _unit_records(unit: str, n: int = 300, *, descending: bool = False) -> list[dict]:
    """One unit's rows, every probability distinct so regime terciles are stable.

    ``descending`` hands the rows in REVERSE date order, so the walk is only
    chronological if ``order_by`` actually sorts them.
    """
    rng = np.random.default_rng(hash(unit) % 2**32)
    probs = list(np.round(np.linspace(0.02, 0.98, n) + rng.uniform(-0.004, 0.004, n), 6))
    days = list(range(n))
    if descending:
        probs, days = probs[::-1], days[::-1]
    return [
        {"event_id": "%s-%03d" % (unit, day), "corpus_unit": unit,
         "event_date": "2020-01-01T%06d" % day,
         "p_base": float(prob), "y": float(rng.random() < prob)}
        for prob, day in zip(probs, days)
    ]


def _per_unit(report: dict) -> dict:
    return {row["corpus_unit"]: row for row in report["by_corpus_unit"]}


def test_per_unit_walk_is_independent_of_the_order_the_units_are_concatenated_in():
    """S50's whole point: no isotonic history may cross a corpus_unit boundary."""
    unit_a, unit_b = _unit_records("A"), _unit_records("B", descending=True)
    kwargs = dict(min_n=200, order_by="event_date", unit_col="corpus_unit")

    forward = build_report(unit_a + unit_b, "synthetic", **kwargs)
    reversed_units = build_report(unit_b + unit_a, "synthetic", **kwargs)
    alone = {"A": build_report(unit_a, "synthetic", **kwargs),
             "B": build_report(unit_b, "synthetic", **kwargs)}

    assert set(_per_unit(forward)) == {"A", "B"}
    for unit in ("A", "B"):
        for key in ("n", "date_min", "date_max", "ece_before", "ece_after"):
            assert _per_unit(forward)[unit][key] == _per_unit(reversed_units)[unit][key]
        # ... and each unit reads exactly what it reads scored on its own.
        assert abs(_per_unit(forward)[unit]["ece_after"] - alone[unit]["ece_after"]) < 1e-12
        assert abs(_per_unit(forward)[unit]["ece_before"] - alone[unit]["ece_before"]) < 1e-12


def test_the_sort_is_reported_and_actually_moves_a_reversed_unit():
    kwargs = dict(min_n=200, order_by="event_date", unit_col="corpus_unit")
    records = _unit_records("A") + _unit_records("B", descending=True)

    walked = build_report(records, "synthetic", **kwargs)
    positional = build_report(records, "synthetic", min_n=200)

    assert walked["order_basis"] == "event_date"
    assert walked["walk_unit_col"] == "corpus_unit"
    assert walked["walk_sort_within_unit_is_noop"] is False   # unit B was reversed
    assert walked["walk_partition_is_identity"] is False      # so is the partition
    assert walked["ece_after"] != positional["ece_after"]     # not cosmetic
    # Default OFF: an untouched caller reads a positional walk and no unit block.
    assert positional["order_basis"] == "POSITIONAL-ORDER"
    assert positional["by_corpus_unit"] is None


def test_the_default_report_still_reproduces_the_landed_nba_artifact():
    """B10 / Q3: the opt-in must not move the bar the S05b landing published."""
    from scripts.platformkit.combo.corpus_cache import load_gate_corpus

    landed_path = _REPO / "docs" / "evidence" / "calibration" / "nba_reliability_2026-09-03.json"
    _require_default_report_evidence(landed_path, _REPO / "data" / "cache" / "combo")
    landed = json.loads(landed_path.read_text(encoding="utf-8"))
    report = build_report(load_gate_corpus("nba"), "nba")

    for key in ("scored_rows", "base_rate", "ece_before", "ece_after", "verdict",
                "sharpness_before", "sharpness_after", "order_basis"):
        assert report[key] == landed[key], key
    assert report["murphy_after"] == landed["murphy_after"]
    assert report["reliability_bins_after"] == landed["reliability_bins_after"]


def test_s156_default_report_guard_skips_only_in_a_worktree(monkeypatch, tmp_path):
    """S156: a clean clone cannot hide missing report evidence in the main repo."""
    absent_artifact, absent_cache = tmp_path / "artifact.json", tmp_path / "combo"
    monkeypatch.setenv("FOUNDRY_WORKTREE", "1")
    with pytest.raises(pytest.skip.Exception):
        _require_default_report_evidence(absent_artifact, absent_cache)
    monkeypatch.delenv("FOUNDRY_WORKTREE")
    monkeypatch.setattr(worktree_marker, "is_worktree_checkout", lambda *a, **k: False)
    with pytest.raises(pytest.fail.Exception, match="main-repo checkout.*artifact.json"):
        _require_default_report_evidence(absent_artifact, absent_cache)
