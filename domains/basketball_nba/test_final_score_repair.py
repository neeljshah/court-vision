"""Per-file test for final_score_repair.py (OT final-score truncation fix).

Acceptance criteria:
1. Known OT-truncation-bug game (0022400002, DET/MIA) reconstructs to the
   true OT-inclusive final (123-121), NOT player_boxscores' tied 111-111.
2. A non-OT game with a pbp file reconstructs to a plausible final and is
   NOT flagged is_ot.
3. Unknown game_id (no cached pbp) returns None -- no crash, no fabrication.
4. build_corrected_finals() writes a parquet with the documented columns
   and at least one truncated OT row.

Run:
  cd /c/Users/neelj/nba-ai-system &&
  python -m pytest domains/basketball_nba/test_final_score_repair.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from domains.basketball_nba.final_score_repair import (
    OUTPUT_COLS,
    build_corrected_finals,
    reconstruct_final_from_pbp,
)

_KNOWN_OT_BUG_GAME = "0022400002"  # DET 123, MIA 121; box/espn both say 111-111


def test_known_ot_bug_game_reconstructs_true_final():
    recon = reconstruct_final_from_pbp(_KNOWN_OT_BUG_GAME)
    assert recon is not None, "expected cached pbp for the known OT-bug game"
    home_pts, away_pts, is_ot = recon
    assert (home_pts, away_pts) == (123, 121)
    assert is_ot is True
    assert home_pts != away_pts, "a real final is never tied"


def test_unknown_game_id_returns_none_no_crash():
    assert reconstruct_final_from_pbp("9999999999") is None


def test_build_corrected_finals_schema_and_content(tmp_path):
    out = tmp_path / "game_finals_corrected.parquet"
    dest = build_corrected_finals(out_path=str(out))
    df = pd.read_parquet(str(dest))
    assert list(df.columns) == list(OUTPUT_COLS)
    assert len(df) > 0
    row = df[df["game_id"] == _KNOWN_OT_BUG_GAME]
    assert not row.empty
    assert bool(row["is_ot"].iloc[0]) is True
    assert bool(row["was_truncated"].iloc[0]) is True
    assert row["home_pts_true"].iloc[0] == 123
    assert row["away_pts_true"].iloc[0] == 121


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
