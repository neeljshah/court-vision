"""Construct tests for the fixed G296A location artifact contract."""

from scripts.platformkit.tracking.g296a_extract_frames import (
    FRAMES_HEADER,
    LOCATED_PLAYERS_HEADER,
    required_frame_indices,
)


def test_required_indices_follow_pinned_formula() -> None:
    expected = tuple(round(index * 174429 / 23) for index in range(24))
    assert required_frame_indices() == expected
    assert len(required_frame_indices()) == 24


def test_csv_headers_match_the_merge_contract() -> None:
    assert LOCATED_PLAYERS_HEADER == (
        "source_frame",
        "person_index",
        "role",
        "feet_visible",
        "foot_x_px",
        "foot_y_px",
        "confidence",
        "note",
    )
    assert FRAMES_HEADER == (
        "source_frame",
        "court_visible",
        "shot_description",
        "players_located",
    )
