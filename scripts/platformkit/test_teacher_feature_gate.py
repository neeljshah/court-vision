"""Artifact fixtures for the fail-closed teacher feature gate."""
from __future__ import annotations

import json

import pytest

from scripts.platformkit.teacher_feature_gate import (
    HARNESS_PASS_10, IMAGE_PX_DECLARED, METRIC_LOCAL, NONE,
    assert_family_unlocked, assert_teacher_columns, corpus_rung,
)


def _csv(root, space="image_px"):
    game = root / "game"
    game.mkdir(parents=True)
    (game / "tracking_data.csv").write_text("coordinate_space\n%s\n" % space)
    return game


def _meta(game):
    (game / "teacher_meta.json").write_text(json.dumps({"segments": [
        {"scale_px_per_ft": 40.0}
    ]}))


def _reports(root, count):
    root.mkdir()
    for index in range(count):
        (root / ("%d.json" % index)).write_text(json.dumps({"passed": True}))


def test_empty_tree_is_none(tmp_path) -> None:
    assert corpus_rung("baseball", tmp_path / "reports", tmp_path / "tracking") == NONE


def test_court_feet_only_does_not_declare_image_pixels(tmp_path) -> None:
    tracking = tmp_path / "tracking"
    _csv(tracking, "court_feet")
    assert corpus_rung("baseball", tmp_path / "reports", tracking) == NONE


def test_nine_passes_is_metric_local_and_ten_is_harness_pass(tmp_path) -> None:
    tracking, reports = tmp_path / "tracking", tmp_path / "reports"
    _meta(_csv(tracking))
    _reports(reports, 9)
    assert corpus_rung("baseball", reports, tracking) == METRIC_LOCAL
    (reports / "10.json").write_text(json.dumps({"passed": True}))
    assert corpus_rung("baseball", reports, tracking) == HARNESS_PASS_10


def test_locked_family_names_the_measured_rung(tmp_path) -> None:
    tracking = tmp_path / "tracking"
    _csv(tracking)
    with pytest.raises(ValueError, match=IMAGE_PX_DECLARED):
        assert_family_unlocked("baseball", "metric_local", tmp_path / "reports", tracking)


def test_runtime_classified_teacher_column_is_rejected() -> None:
    with pytest.raises(ValueError, match="TRAINING_ONLY"):
        assert_teacher_columns(["market_price"])
