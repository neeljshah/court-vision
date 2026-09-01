"""Tests for the S4a confirmed-game emission path.

Run: python -m pytest scripts/platformkit/test_baseball_s4_emission.py -q
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from scripts.platformkit.baseball_s4_emission import corrected_manifest, reemit


def _census(tmp_path):
    frame = tmp_path / "npb__game_f00000000.jpg"
    frame.touch()
    return pd.DataFrame([{
        "clip": "data/footage_corpus/npb__npb_3PwJwWdTMek.mp4",
        "source_frame": 12,
        "jpeg_path": str(frame),
    }])


def test_confirmed_game_without_homography_is_unsolved_not_non_play(tmp_path):
    manifest = corrected_manifest(_census(tmp_path))

    assert manifest.to_dict("records") == [{"frame": 12, "status": "unsolved"}]


def test_reemit_writes_counted_sidecars(tmp_path):
    census_path = tmp_path / "census.csv"
    _census(tmp_path).to_csv(census_path, index=False)

    counts = reemit(census_path, tmp_path / "out")
    payload = json.loads((tmp_path / "out" / "tracking_completeness.json").read_text())

    assert counts == {"decoded_frames": 1, "solved": 0, "unsolved": 1, "non_play": 0}
    assert payload["classification"] == "confirmed_game_source_not_pitch_geometry_gate"


def test_unconfirmed_source_is_rejected(tmp_path):
    census = _census(tmp_path)
    census.loc[0, "clip"] = "data/footage_corpus/mlb__talk_show.mp4"

    with pytest.raises(ValueError, match="expected the one confirmed NPB source"):
        corrected_manifest(census)
