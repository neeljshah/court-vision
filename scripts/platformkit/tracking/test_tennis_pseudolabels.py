"""Focused proof for tennis pseudo-label emission and deterministic holdout selection."""
import numpy as np

from scripts.platformkit.tracking.tennis_pseudolabels import label_frame, select_holdout


class _Adapter:
    def __init__(self):
        self._last_fresh_corners = np.float32(((0, 0), (0, 36), (78, 0), (78, 36)))

def test_known_homography_emits_keypoints_visibility_and_provenance(monkeypatch):
    adapter = _Adapter()
    monkeypatch.setattr(adapter, "_calibrated_homography",
                        lambda _frame: (np.eye(3), "solved", "ready", 1.25, 4), raising=False)
    frame = np.zeros((40, 70, 3), dtype=np.uint8)
    row = label_frame(adapter, frame, "match.mp4", 12, "10-20")

    assert row is not None and len(row["keypoints"]) == 14
    assert row["keypoints"][0] == {"name": "doubles_bl", "x": 0.0, "y": 0.0, "visible": True}
    assert row["keypoints"][1]["visible"] is False  # x=78 exceeds the 70-pixel frame width.
    assert row["keypoints"][3]["visible"] is True
    assert row["keypoints"][8]["visible"] is True
    assert row["keypoints"][11]["visible"] is True
    provenance = row["provenance"]
    assert provenance == {"range_id": "10-20", "solve_type": "fresh", "drift_px": 1.25,
                          "drift_evidence_count": 4, "line_reprojection_residual_px": 0.0}
    assert monkeypatch is not None


def test_holdout_selection_is_deterministic():
    labels = [{"frame": index} for index in range(10)]
    assert [row["frame"] for row in select_holdout(labels, 4)] == [0, 3, 6, 9]
    assert select_holdout(labels, 0) == []
