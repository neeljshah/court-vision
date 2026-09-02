"""Focused unit checks for G110 pixel-comparison record handling."""
import numpy as np

from scripts.platformkit.g110_tile_nonreproducibility import _records, pixel_stats


def test_g110_pixel_stats_and_record_boundaries() -> None:
    first = b"one"
    second = b"two"
    payload = len(first).to_bytes(4, "big") + first + len(second).to_bytes(4, "big") + second
    assert _records(payload, 2) == [first, second]
    try:
        _records(payload + b"x", 2)
    except ValueError as error:
        assert "unexpected bytes" in str(error)
    else:
        raise AssertionError("trailing probe data must fail")
    stats = pixel_stats(np.zeros((2, 2, 3), dtype=np.uint8), np.array([[[0, 0, 0], [1, 0, 0]], [[0, 0, 0], [0, 0, 0]]], dtype=np.uint8))
    assert stats["pixel_equal"] == "false"
    assert stats["changed_pixels"] == "1"
    assert stats["max_abs_channel_delta"] == "1"
