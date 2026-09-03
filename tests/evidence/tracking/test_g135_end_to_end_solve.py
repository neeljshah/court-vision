"""Focused regression for G135's all-four matched-role enumeration."""
from __future__ import annotations

import pytest

from scripts.platformkit.g135_end_to_end_solve import qualifying_frames


def test_g135_requires_one_unique_match_for_each_paint_role() -> None:
    frame = {"clip": "wnba__fixture", "frame_index": "12"}
    complete = [
        {**frame, "role": role, "stable_detected": "true"}
        for role in ("baseline", "free_throw", "lane_left", "lane_right")
    ]
    assert qualifying_frames(complete) == [("wnba__fixture", "12")]
    assert qualifying_frames([*complete[:-1], {**frame, "role": "lane_right", "stable_detected": "false"}]) == []
    with pytest.raises(ValueError, match="duplicate role row"):
        qualifying_frames([*complete, complete[0]])
