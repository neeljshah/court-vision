"""Focused leak and chronology tests for teacher_student_ab.

Run: python -m pytest scripts/platformkit/test_teacher_student_ab.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from scripts.platformkit.teacher_student_ab import build_features, diagnose, evaluate_ab, expanding_folds, tracking_targets


def _inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    tracking = []
    for game in range(1, 7):
        game_id = "00224000{0:02d}".format(game)
        for player in (10, 20):
            tracking.append({"gameId": game_id, "personId": player, "gameDate": "2024-01-{0:02d}".format(game),
                             "minutes": "{0}:30".format(20 + game), "touches_per36_l5": game + player})
    base = pd.DataFrame(tracking)
    load = base.loc[:, ["gameId", "personId"]].assign(days_rest=2.0)
    embeddings = base.loc[:, ["gameId", "personId"]].assign(style_embedding_1=0.5)
    return base, load, embeddings


def test_minutes_baseline_features_are_truncation_invariant() -> None:
    """Changing future realized minutes cannot change prior feature rows."""
    tracking, load, embeddings = _inputs()
    full = build_features(tracking, load, embeddings)
    cutoff = pd.Timestamp("2024-01-05")
    changed = tracking.copy()
    changed.loc[changed.gameId >= "0022400005", "minutes"] = "999:00"
    altered = build_features(changed, load, embeddings)
    columns = ["gameId", "personId", "minutes_expanding", "minutes_l5"]
    assert_frame_equal(full.loc[full.gameDate < cutoff, columns].reset_index(drop=True),
                       altered.loc[altered.gameDate < cutoff, columns].reset_index(drop=True))


def test_build_features_normalises_string_and_integer_game_ids() -> None:
    """Tracking targets join integer companion parquet IDs through ten-digit keys."""
    tracking, load, embeddings = _inputs()
    tracking["gameId"] = tracking["gameId"].astype(int)
    load["gameId"] = load["gameId"].astype(int)
    embeddings["gameId"] = embeddings["gameId"].astype(int)

    result = build_features(tracking, load, embeddings)

    assert len(result) == len(tracking)
    assert result["gameDate"].notna().all()
    assert result["gameId"].str.len().eq(10).all()
    assert result["personId"].dtype == "int64"


def test_tracking_targets_parse_minutes_strings_without_boxscores() -> None:
    """The primary corpus supplies current-game minutes from its MM:SS values."""
    tracking, _, _ = _inputs()

    targets = tracking_targets(tracking)

    assert targets["minutes"].iloc[0] == pytest.approx(21.5)
    assert len(targets) == len(tracking)


def test_diagnose_reports_exact_pair_misses_and_categories() -> None:
    """Key diagnosis separates a different-game player from an absent player."""
    targets = pd.DataFrame([
        {"gameId": "0022400001", "personId": 10, "playerName": "Matched", "minutes": 20},
        {"gameId": "0022400001", "personId": 20, "playerName": "Other game", "minutes": 0},
        {"gameId": "0022400002", "personId": 30, "playerName": "Absent", "minutes": 0},
    ])
    tracking = pd.DataFrame([
        {"gameId": 22400001, "personId": 10},
        {"gameId": 22400003, "personId": 20},
    ])

    report = diagnose(targets, tracking)

    assert report["matched_pairs"] == 1
    assert report["pair_coverage_pct"] == pytest.approx(100.0 / 3.0)
    assert report["misses"] == {
        "count": 2,
        "person_present_different_game": 1,
        "person_never_in_tracking": 1,
        "game_never_in_tracking": 1,
    }
    assert [sample["playerName"] for sample in report["miss_samples"]] == ["Other game", "Absent"]


def test_fold_assertion_fires_on_shuffled_dates() -> None:
    """Chronological fold construction refuses an unsorted input frame."""
    dates = pd.date_range("2024-01-01", periods=6, freq="D")
    frame = pd.DataFrame({"gameDate": dates, "minutes": range(6)}).iloc[[1, 0, 2, 3, 4, 5]]
    with pytest.raises(AssertionError, match="sorted"):
        list(expanding_folds(frame, folds=4))


def test_tracking_arm_uses_signal_bearing_columns() -> None:
    """A live tracking design matrix improves when tracking carries the target signal."""
    signal = [((index * 17) % 11) for index in range(240)]
    frame = pd.DataFrame({
        "gameDate": pd.date_range("2024-01-01", periods=len(signal), freq="D"),
        "minutes": [float(value * 3) for value in signal],
        "minutes_expanding": 30.0,
        "minutes_l5": 30.0,
        "tracking_signal_a_per36_l5": signal,
        "tracking_signal_b_per36_l5": signal,
        "tracking_signal_c_per36_l10": signal,
    })
    tracking_columns = ["tracking_signal_a_per36_l5", "tracking_signal_b_per36_l5", "tracking_signal_c_per36_l10"]

    report = evaluate_ab(frame, tracking_columns, folds=4)

    assert report["pooled"]["verdict"] == "IMPROVED"
    assert report["pooled"]["delta"] < 0.0
    for fold in report["folds"]:
        assert fold["tracking_train_columns"][-3:] == tracking_columns
        assert all(rate >= 0.50 for rate in fold["tracking_non_null_rates"].values())


def test_sparse_tracking_matrix_is_invalid_features() -> None:
    """A key join cannot validate an arm whose tracking columns are absent."""
    frame = pd.DataFrame({
        "gameDate": pd.date_range("2024-01-01", periods=20, freq="D"),
        "minutes": range(20),
        "minutes_expanding": 30.0,
        "minutes_l5": 30.0,
        "only_tracking_per36_l5": [None] * 20,
    })

    report = evaluate_ab(frame, ["only_tracking_per36_l5"], folds=4)

    assert report["pooled"]["verdict"] == "INVALID (features)"
    assert report["pooled"]["mae_track"] is None
