"""Per-file test for nba_interaction_stability: synthetic 2-season frames
with a KNOWN engineered correlation (perfectly correlated pairwise gravity,
too-few-points lineup overlap) so the pearson_r + the interpretability
floor are both hand-checkable, not just "runs without crashing".

Run: python -m pytest scripts/platformkit/intel_validation/test_nba_interaction_stability.py -q
"""
from __future__ import annotations

from scripts.platformkit.intel_validation import nba_interaction_stability as m


def test_stability_for_metric_reports_honest_pearson_r_above_floor(monkeypatch):
    monkeypatch.setattr(m, "SEASONS", ["a", "b"])
    monkeypatch.setattr(m, "MIN_OVERLAP_FOR_CORR", 3)
    # season "a": values 1..5 for pairs 0..4; season "b": IDENTICAL values
    # for the SAME pairs -> perfect correlation (r=1.0), n_overlap=5.
    import pandas as pd
    frame_a = pd.DataFrame({
        "team_id": [1] * 5, "player_x": list(range(5)), "player_y": list(range(5)),
        "efg_delta": [0.1, 0.2, 0.3, 0.4, 0.5],
    })
    frame_b = frame_a.copy()  # identical effect sizes -> perfect stability
    frames = {"a": frame_a, "b": frame_b}

    rows = m.stability_for_metric(frames, ["team_id", "player_x", "player_y"], "efg_delta")
    assert len(rows) == 1  # only one season-pair combo when SEASONS has 2 entries
    row = rows[0]
    assert row["n_overlap"] == 5
    assert row["interpretable"] is True
    assert abs(row["pearson_r"] - 1.0) < 1e-9


def test_stability_below_min_overlap_is_honestly_uninterpretable(monkeypatch):
    monkeypatch.setattr(m, "SEASONS", ["a", "b"])
    monkeypatch.setattr(m, "MIN_OVERLAP_FOR_CORR", 30)
    import pandas as pd
    frame_a = pd.DataFrame({
        "team_id": [1, 1], "player_x": [0, 1], "player_y": [0, 1], "efg_delta": [0.1, 0.2],
    })
    frame_b = frame_a.copy()
    frames = {"a": frame_a, "b": frame_b}

    rows = m.stability_for_metric(frames, ["team_id", "player_x", "player_y"], "efg_delta")
    row = rows[0]
    assert row["n_overlap"] == 2
    assert row["interpretable"] is False
    assert row["pearson_r"] is None  # too few points to mean anything -- not fabricated as 0 or 1


def test_stability_zero_overlap_does_not_crash(monkeypatch):
    monkeypatch.setattr(m, "SEASONS", ["a", "b"])
    monkeypatch.setattr(m, "MIN_OVERLAP_FOR_CORR", 3)
    import pandas as pd
    frame_a = pd.DataFrame({"team_id": [1], "player_x": [0], "player_y": [0], "efg_delta": [0.1]})
    frame_b = pd.DataFrame({"team_id": [2], "player_x": [9], "player_y": [9], "efg_delta": [0.2]})
    frames = {"a": frame_a, "b": frame_b}

    rows = m.stability_for_metric(frames, ["team_id", "player_x", "player_y"], "efg_delta")
    row = rows[0]
    assert row["n_overlap"] == 0
    assert row["pearson_r"] is None
