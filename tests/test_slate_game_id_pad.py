"""Tests for the gated CV_SLATE_PAD_GAMEID fix (cv_fix_build_slate._slate_game_id).

Default (flag OFF) MUST be byte-identical to the legacy int(gid) behavior (strips
leading zeros). Flag ON preserves the zero-padded 10-digit NBA id so the live
in-game regrade snapshot lookup matches.
"""
import importlib
import os

import pytest

cfs = importlib.import_module("scripts.cv_fix_build_slate")


@pytest.fixture(autouse=True)
def _clear_flag(monkeypatch):
    monkeypatch.delenv("CV_SLATE_PAD_GAMEID", raising=False)
    yield


def test_default_off_is_legacy_int(monkeypatch):
    monkeypatch.delenv("CV_SLATE_PAD_GAMEID", raising=False)
    out = cfs._slate_game_id("0042500317")
    assert out == 42500317 and isinstance(out, int), "default must match legacy int(gid)"


def test_flag_on_preserves_padding(monkeypatch):
    monkeypatch.setenv("CV_SLATE_PAD_GAMEID", "1")
    out = cfs._slate_game_id("0042500317")
    assert out == "0042500317" and isinstance(out, str), "ON must keep the zero-padded id"


def test_flag_on_pads_unpadded_numeric(monkeypatch):
    monkeypatch.setenv("CV_SLATE_PAD_GAMEID", "1")
    # an already-stripped int-like string re-pads to 10 digits
    assert cfs._slate_game_id("42500317") == "0042500317"


def test_flag_on_passes_through_non_numeric(monkeypatch):
    monkeypatch.setenv("CV_SLATE_PAD_GAMEID", "1")
    assert cfs._slate_game_id("KAMBI_abc123") == "KAMBI_abc123"


def test_padded_id_matches_live_snapshot_key():
    """The whole point: ON output must equal the data/live snapshot stem convention."""
    os.environ["CV_SLATE_PAD_GAMEID"] = "1"
    try:
        gid_out = cfs._slate_game_id("0042500317")
        snapshot_stem_key = "0042500317_1730000000".split("_")[0]  # router _get_live_dir_index
        assert str(gid_out) == snapshot_stem_key
    finally:
        os.environ.pop("CV_SLATE_PAD_GAMEID", None)
