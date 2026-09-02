"""Focused checks for the G103 source-tile record protocol."""
from scripts.platformkit.g103_g68_tile_recipe import _records


def test_g103_pod_record_parser_rejects_trailing_or_truncated_data() -> None:
    first = b"one"
    second = b"two"
    encoded = len(first).to_bytes(4, "big") + first + len(second).to_bytes(4, "big") + second
    assert _records(encoded, 2) == [first, second]
    try:
        _records(encoded + b"x", 2)
    except ValueError as error:
        assert "unexpected bytes" in str(error)
    else:
        raise AssertionError("trailing pod bytes must fail")
    try:
        _records(encoded[:-1], 2)
    except ValueError as error:
        assert "truncated" in str(error)
    else:
        raise AssertionError("truncated pod records must fail")
