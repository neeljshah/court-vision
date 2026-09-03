"""Focused tests for the S204 close-reference calibration reporter."""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.s204_close_reference import _score


def _frame(n: int, *, close_shift: float = 0.0) -> pd.DataFrame:
    rows = []
    for index in range(n):
        probability = 0.25 if index % 2 else 0.75
        rows.append({
            "event_id": "event-%03d" % index, "corpus_unit": "unit-%03d" % index,
            "event_date": "2026-01-%02d" % ((index % 28) + 1), "y": float(index % 2),
            "p_base": probability, "p_model": probability, "p_close": probability + close_shift,
            "close_source": "pregame_last_tick_before_commence",
        })
    return pd.DataFrame(rows)


def test_s204_scores_identical_pairs_with_ten_bins_and_clustered_status() -> None:
    frame = _frame(30)
    report, pairs, excluded = _score("synthetic", frame, pd.Series(True, index=frame.index), [])

    assert len(pairs) == 30 and len(excluded) == 0
    assert report["paired_rows"] == 30
    assert report["dropped_after_pairing"] == 0
    assert report["n_eff"] == 30
    assert report["comparison_status"] == "MATCH"
    assert report["brier_delta_close_minus_model"] == 0.0
    assert len(report["model"]["reliability_bins"]) == 10
    assert report["model"] == report["close"]


def test_s204_marks_fewer_than_thirty_clusters_not_scorable_and_names_exclusions() -> None:
    frame = _frame(29)
    frame.loc[0, "p_close"] = np.nan
    frame.loc[1, "close_source"] = "first_inplay_tick"
    report, pairs, excluded = _score(
        "synthetic", frame, frame["close_source"].eq("pregame_last_tick_before_commence"), [])

    assert len(pairs) == 27
    assert report["n_eff"] == 27
    assert report["comparison_status"] == "NOT SCORABLE"
    assert report["reason"] == "fewer than 30 corpus_unit clusters"
    assert sorted(excluded["reason"].tolist()) == ["inplay_close_source", "null_price"]


def test_s204_reports_one_cluster_as_not_scorable_without_fabricating_a_ci() -> None:
    frame = _frame(3)
    frame["corpus_unit"] = "one-unit"
    report, _, _ = _score("synthetic", frame, pd.Series(True, index=frame.index), [])

    assert report["n_eff"] == 1
    assert report["ci95"] is None
    assert report["comparison_status"] == "NOT SCORABLE"
