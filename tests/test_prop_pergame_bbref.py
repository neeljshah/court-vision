"""BBRef advanced features in prop_pergame — null-safe loader + correct join."""
from __future__ import annotations

import json
import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    _BBREF_DEFAULTS,
    _BBREF_KEYS,
    build_bbref_advanced,
    feature_columns,
)


def test_bbref_columns_present_in_feature_columns():
    cols = feature_columns()
    for k in _BBREF_KEYS:
        assert f"bbref_{k}" in cols, f"missing column: bbref_{k}"


def test_bbref_defaults_when_dir_missing():
    """build_bbref_advanced returns defaults when the dir doesn't exist."""
    b = build_bbref_advanced(bbref_dir="/definitely/nonexistent/path")
    feats = b.features(2544, "2024-25")  # LeBron's player_id
    assert feats == dict(_BBREF_DEFAULTS)
    assert all(v == 0.0 for v in feats.values())


def test_bbref_defaults_for_unknown_player():
    """A bogus player_id falls back to zeros without raising."""
    b = build_bbref_advanced()
    feats = b.features(99999999, "2024-25")  # not in nba_api static list
    assert feats == dict(_BBREF_DEFAULTS)


def test_bbref_loads_real_data_for_known_player(tmp_path):
    """Synthetic mini-BBRef file → exact player lookup works."""
    season_dir = tmp_path
    fixture = [
        {
            "player_name": "LeBron James",
            "usg_pct": 28.0, "ts_pct": 0.58, "three_par": 0.30, "ftr": 0.20,
            "ast_pct": 41.2, "stl_pct": 1.3, "blk_pct": 1.0, "tov_pct": 12.0,
            "ws_per_48": 0.17, "per": 24.0, "obpm": 4.0, "dbpm": 1.5,
        },
        {
            # Note: BBRef cache stores names mangled (UTF-8 bytes mis-encoded as
            # Latin-1). The loader reverses the mojibake. Test the unmangle:
            # bytes for "Nikola Jokić" stored as if Latin-1 -> the literal below.
            "player_name": "Nikola JokiÄ",
            "usg_pct": 30.0, "ts_pct": 0.66, "three_par": 0.20, "ftr": 0.30,
            "ast_pct": 50.0, "stl_pct": 1.8, "blk_pct": 1.5, "tov_pct": 15.0,
            "ws_per_48": 0.30, "per": 32.0, "obpm": 9.0, "dbpm": 4.0,
        },
    ]
    (season_dir / "bbref_advanced_2024-25.json").write_text(json.dumps(fixture))

    b = build_bbref_advanced(bbref_dir=str(season_dir))

    # LeBron James: player_id 2544 (nba_api static)
    feats = b.features(2544, "2024-25")
    assert feats["bbref_usg_pct"] == pytest.approx(28.0)
    assert feats["bbref_ts_pct"] == pytest.approx(0.58)
    assert feats["bbref_per"] == pytest.approx(24.0)
    assert feats["bbref_obpm"] == pytest.approx(4.0)
    assert feats["bbref_dbpm"] == pytest.approx(1.5)

    # Jokic: player_id 203999
    feats_jok = b.features(203999, "2024-25")
    assert feats_jok["bbref_per"] == pytest.approx(32.0)
    assert feats_jok["bbref_obpm"] == pytest.approx(9.0)
    assert feats_jok["bbref_ts_pct"] == pytest.approx(0.66)


def test_bbref_corrupt_file_does_not_raise(tmp_path):
    (tmp_path / "bbref_advanced_2024-25.json").write_text("not valid json {")
    b = build_bbref_advanced(bbref_dir=str(tmp_path))
    # The corrupt file is skipped; an unknown player still gets defaults.
    feats = b.features(2544, "2024-25")
    assert feats == dict(_BBREF_DEFAULTS)


def test_bbref_real_data_for_mikal_bridges():
    """End-to-end with the real cached file. Mikal Bridges (pid=1628969) →
    bbref_ts_pct should be 0.585 in 2024-25 (verified by Opus during PRED-20)."""
    b = build_bbref_advanced()
    feats = b.features(1628969, "2024-25")
    if feats == dict(_BBREF_DEFAULTS):
        pytest.skip("real BBRef cache absent on this machine")
    assert feats["bbref_ts_pct"] == pytest.approx(0.585, abs=0.01)
    assert feats["bbref_usg_pct"] == pytest.approx(19.6, abs=0.1)
