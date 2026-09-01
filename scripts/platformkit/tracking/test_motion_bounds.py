"""Tests for empirical motion-bound fitting."""
import json

import pandas as pd

from scripts.platformkit.tracking.motion_bounds import fit_motion_bounds, write_motion_bounds
from scripts.platformkit.tracking_harness import SPORTS


def _constant_steps() -> pd.DataFrame:
    return pd.DataFrame({"frame": range(8), "player_id": [7] * 8, "cls": ["player"] * 8,
                         "x_position": [3.0 * frame for frame in range(8)], "y_position": [0.0] * 8})


def test_constant_steps_and_harness_derived_units(tmp_path):
    source = tmp_path / "tracking_data.csv"
    _constant_steps().to_csv(source, index=False)
    basketball = fit_motion_bounds([source], "basketball")
    assert basketball["p95"] == basketball["p99"] == 3.0
    assert basketball["units"] == "ft"
    soccer = fit_motion_bounds([source], "soccer")
    football = fit_motion_bounds([source], "football")
    assert soccer["units"] == football["units"] == "m"
    assert SPORTS["basketball"]["bounds"] == SPORTS["wnba"]["bounds"]


def test_write_preserves_other_sport_entries(tmp_path):
    source = tmp_path / "tracking_data.csv"
    _constant_steps().to_csv(source, index=False)
    output = tmp_path / "motion_bounds.json"
    write_motion_bounds([source], "basketball", output)
    write_motion_bounds([source], "soccer", output)
    saved = json.loads(output.read_text())
    assert set(saved) == {"basketball", "soccer"}
