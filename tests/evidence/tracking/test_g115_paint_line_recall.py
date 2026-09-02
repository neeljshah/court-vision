"""Focused checks for the fixed G115 G110-exclusion boundary."""
from scripts.platformkit.g115_paint_line_recall import EXCLUSIONS, valid_manifest


def test_g115_uses_exactly_the_g110_same_picture_subset() -> None:
    rows = valid_manifest()
    identities = {(row["clip"], row["frame_index"]) for row in rows}
    assert len(rows) == 30
    assert len(identities) == 30
    assert not EXCLUSIONS & identities
