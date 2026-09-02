"""Focused regression checks for the audited G84 frame selection."""
from scripts.platformkit.g84_candidate_line_quality import _audited_positives


def test_g84_uses_seeded_g76_positive_frames_from_every_clip() -> None:
    rows = _audited_positives()
    assert len(rows) == 33
    assert {row["g76_label"] for row in rows} == {"PAINT_SOLVABLE"}
    assert len({row["clip"] for row in rows}) == 11
