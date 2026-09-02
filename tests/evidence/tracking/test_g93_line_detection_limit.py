"""Focused unit checks for the preregistered G93 correspondence rule."""
from scripts.platformkit.g93_line_detection_limit import _matches, wilson_interval


def test_g93_correspondence_rule_and_wilson_interval() -> None:
    hand = ((100, 100), (300, 100))
    assert _matches(((125, 106), (225, 106)), hand)
    assert not _matches(((125, 113), (225, 113)), hand)
    assert not _matches(((125, 100), (225, 150)), hand)
    assert not _matches(((40, 100), (60, 100)), hand)
    low, high = wilson_interval(0, 33)
    assert round(low, 6) == 0.0
    assert round(high, 6) == 0.104270
