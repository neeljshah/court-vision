from scripts.platformkit.demo_render import caption_lines


def test_caption_keeps_image_space_explicit() -> None:
    first, second = caption_lines("NCAA basketball", "image_px", "observed centroid tracks")
    assert "image px" in first
    assert "court" not in first.lower()
    assert second == "CourtVision tracking teacher -- training-only corpus"


def test_caption_keeps_court_feet_explicit() -> None:
    first, _ = caption_lines("Tennis", "court_feet", "solved homography rows")
    assert "court feet" in first
