"""Per-file test for claims_shift_framing.py -- synthetic frames, hand-computed
ranking math, n-floor filtering, edge_claimed=False.
Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/test_claims_shift_framing.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.mlb import claims_shift_framing as csf


def _synthetic_taken_pitches(n_per_catcher: int) -> pd.DataFrame:
    """2 catchers, all pitches ON the edge shell (plate_x=0.83), catcher A all
    called_strike, catcher B all ball -- league_rate must land at exactly 0.5."""
    rows = []
    for cid, desc in ((111, "called_strike"), (222, "ball")):
        for _ in range(n_per_catcher):
            rows.append({"fielder_2": cid, "description": desc, "plate_x": 0.83, "plate_z": 2.5,
                         "sz_top": 3.5, "sz_bot": 1.5, "strikes": 0, "balls": 0,
                         "game_date": "2023-04-01"})
    return pd.DataFrame(rows)


def test_build_framing_claim_hand_computed(tmp_path):
    df = _synthetic_taken_pitches(n_per_catcher=40)
    claim = csf.build_framing_claim("2023", df_raw=df, out_dir=tmp_path, floor=40)
    assert claim["league_rate"] == 0.5
    ranking = {r["catcher_id"]: r for r in claim["ranking"]}
    assert ranking[111]["value"] == 1.0
    assert ranking[111]["vs_league"] == 0.5
    assert ranking[222]["value"] == 0.0
    assert ranking[222]["vs_league"] == -0.5
    assert claim["n_considered"] == 2
    assert claim["n_excluded_below_floor"] == 0
    assert claim["edge_claimed"] is False


def test_build_framing_claim_floor_excludes_thin_catcher(tmp_path):
    df = _synthetic_taken_pitches(n_per_catcher=40)
    claim = csf.build_framing_claim("2023", df_raw=df, out_dir=tmp_path, floor=41)
    assert claim["ranking"] == []
    assert claim["n_excluded_below_floor"] == 2


def _synthetic_gb(n_shifted: int, n_standard: int) -> pd.DataFrame:
    """1 batter: all shifted GBs are outs (babip_shifted=0.0), all standard GBs
    are hits (babip_standard=1.0) -> delta=1.0, plus a HR row (must be excluded)
    and a non-GB row (must be excluded)."""
    rows = []
    for _ in range(n_shifted):
        rows.append({"batter": 7, "type": "X", "bb_type": "ground_ball", "events": "field_out",
                     "if_fielding_alignment": "Infield shade", "game_date": "2023-04-01"})
    for _ in range(n_standard):
        rows.append({"batter": 7, "type": "X", "bb_type": "ground_ball", "events": "single",
                     "if_fielding_alignment": "Standard", "game_date": "2023-04-01"})
    rows.append({"batter": 7, "type": "X", "bb_type": "ground_ball", "events": "home_run",
                 "if_fielding_alignment": "Infield shade", "game_date": "2023-04-01"})
    rows.append({"batter": 7, "type": "X", "bb_type": "fly_ball", "events": "field_out",
                 "if_fielding_alignment": "Standard", "game_date": "2023-04-01"})
    return pd.DataFrame(rows)


def test_build_shift_vulnerability_claim_hand_computed(tmp_path):
    df = _synthetic_gb(n_shifted=60, n_standard=60)
    claim = csf.build_shift_vulnerability_claim("2023", df_raw=df, out_dir=tmp_path, floor=50)
    assert len(claim["ranking"]) == 1
    row = claim["ranking"][0]
    assert row["batter_id"] == 7
    assert row["babip_shifted"] == 0.0
    assert row["babip_standard"] == 1.0
    assert row["value"] == 1.0  # babip_delta = standard - shifted
    assert row["n_shifted"] == 60
    assert claim["edge_claimed"] is False


def test_build_shift_vulnerability_claim_floor_excludes_thin_batter(tmp_path):
    df = _synthetic_gb(n_shifted=30, n_standard=60)
    claim = csf.build_shift_vulnerability_claim("2023", df_raw=df, out_dir=tmp_path, floor=50)
    assert claim["ranking"] == []
    assert claim["n_excluded_below_floor"] == 1


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
