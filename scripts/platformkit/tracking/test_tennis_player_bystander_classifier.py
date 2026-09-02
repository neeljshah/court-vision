"""Focused G70 checks for clip-disjoint evaluation and scored metrics."""
from scripts.platformkit.tracking.tennis_player_bystander_classifier import clip_folds, metric


def test_clip_folds_do_not_leak_and_metrics_include_specification_baseline() -> None:
    rows = [
        {"match": clip, "label": label}
        for clip in ("clip_a", "clip_b", "clip_c")
        for label in ("player", "non_player_person")
    ]
    folds = clip_folds(rows)
    assert len(folds) == 3
    for fold in folds:
        assert fold["held_out_clip"] not in fold["train_clips"]
        assert {rows[index]["match"] for index in fold["test_indices"]} == {fold["held_out_clip"]}
    report = metric(rows, ["player", "non_player_person"] * 3)
    assert report["accuracy"] == 1.0
    assert report["specification_majority_baseline"] == 155 / 210
    assert report["per_class_recall"]["player"]["recall"] == 1.0
