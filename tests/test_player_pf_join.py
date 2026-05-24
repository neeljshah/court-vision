"""
test_player_pf_join.py — cycle 91b (loop 5) tests for the player_pf parquet
backfill + per-(player_id, game_date) PF/36 rolling join in build_pergame_dataset.

Validates:
1. Parquet absent  → no-op back-compat (build_player_pf returns empty wrapper).
2. Parquet present → join works; sample row has pf field.
3. season_pf_per_36 has NO leakage — target game is excluded.
4. Unknown (player_id, game_date) → pf=NaN/None, no crash.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    _PlayerPF,
    build_player_pf,
)


def test_parquet_absent_is_noop():
    """Missing parquet path → empty wrapper; every query returns None."""
    wrapper = build_player_pf(
        pf_path="/definitely/not/a/file.parquet",
        per36_path="/definitely/not/a/file.parquet",
    )
    assert isinstance(wrapper, _PlayerPF)
    assert len(wrapper) == 0
    assert wrapper.pf(201939, "2024-10-22") is None
    assert wrapper.season_pf_per_36(201939, "2024-10-22") is None


def test_parquet_present_join_works(tmp_path):
    """Parquet present → pf lookup returns the right value for a sample row."""
    pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")
    import pandas as pd

    pf_path = tmp_path / "player_pf.parquet"
    pd.DataFrame([
        {"game_id": "0022400061", "player_id": 1627759, "team_abbreviation": "BOS",
         "game_date": "2024-10-22", "pf": 3.0, "min": 29.9},
        {"game_id": "0022400061", "player_id": 1628369, "team_abbreviation": "BOS",
         "game_date": "2024-10-22", "pf": 1.0, "min": 30.3},
    ]).to_parquet(pf_path, index=False)

    wrapper = build_player_pf(pf_path=str(pf_path), per36_path="/nope")
    assert len(wrapper) == 2
    assert wrapper.pf(1627759, "2024-10-22") == pytest.approx(3.0)
    assert wrapper.pf(1628369, "2024-10-22") == pytest.approx(1.0)
    # per36 absent → still None even when pf is loaded
    assert wrapper.season_pf_per_36(1627759, "2024-10-22") is None


def test_rolling_pf_per_36_no_leakage(tmp_path):
    """compute_pf_per36 must exclude the target game (shift(1) before sum)."""
    pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")
    import pandas as pd

    # Import the aggregator's compute helper directly.
    sys.path.insert(0, os.path.join(PROJECT_DIR, "scripts"))
    from aggregate_pf_per_36 import compute_pf_per36  # noqa: PLC0415

    df = pd.DataFrame([
        {"player_id": 99, "game_date": "2024-10-22", "pf": 4.0, "min": 36.0},
        {"player_id": 99, "game_date": "2024-10-23", "pf": 2.0, "min": 36.0},
        {"player_id": 99, "game_date": "2024-10-24", "pf": 6.0, "min": 36.0},
    ])
    out = compute_pf_per36(df).set_index("game_date")["season_pf_per_36"]
    # Game 1: no prior history → NaN.
    assert pd.isna(out["2024-10-22"])
    # Game 2: only game 1 contributes → 4 PF / 36 min * 36 = 4.0.
    assert out["2024-10-23"] == pytest.approx(4.0)
    # Game 3: games 1+2 contribute → (4+2) / 72 * 36 = 3.0.
    # (NOT 4.0 — which would mean game 3 leaked into its own per36.)
    assert out["2024-10-24"] == pytest.approx(3.0)


def test_unknown_key_returns_none(tmp_path):
    """Unknown (player_id, game_date) → None; no crash, no KeyError."""
    pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")
    import pandas as pd

    pf_path = tmp_path / "player_pf.parquet"
    pd.DataFrame([
        {"game_id": "0022400061", "player_id": 1627759, "team_abbreviation": "BOS",
         "game_date": "2024-10-22", "pf": 3.0, "min": 29.9},
    ]).to_parquet(pf_path, index=False)

    wrapper = build_player_pf(pf_path=str(pf_path), per36_path="/nope")
    # Unknown pid
    assert wrapper.pf(999999, "2024-10-22") is None
    # Unknown date
    assert wrapper.pf(1627759, "1999-01-01") is None
    # Non-int pid → still None, no crash
    assert wrapper.pf("not_an_int", "2024-10-22") is None
    assert wrapper.season_pf_per_36(None, "2024-10-22") is None
