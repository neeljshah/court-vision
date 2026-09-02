"""Focused non-GPU checks for G17C role-classifier measurement helpers."""
from scripts.platformkit.tracking.soccer_role_classifier_v3 import CLASS_NAMES, grouped_folds, summarize_predictions


def test_grouped_cv_covers_300_crops_without_source_frame_leakage() -> None:
    rows = []
    for frame in range(30):
        role = CLASS_NAMES[frame % len(CLASS_NAMES)]
        rows.extend({"crop_filename": "%03d_%d.jpg" % (frame, copy), "source_frame": "F%03d" % frame, "class": role}
                    for copy in range(10))
    folds = grouped_folds(rows)
    assert set(folds) == set(range(5))
    assert all(len({folds[i] for i, row in enumerate(rows) if row["source_frame"] == frame}) == 1
               for frame in {row["source_frame"] for row in rows})
    metric = summarize_predictions(rows, [row["class"] for row in rows])
    assert metric == {"n": 300, "accuracy": 1.0, "majority_class_baseline": 1 / 3,
                      "per_class_recall": {name: 1.0 for name in CLASS_NAMES}}
