"""Per-file test for claims_fielding_alignment.py -- synthetic frames, hand-computed
split math, edge_claimed=False, and n-floor filtering.
Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/test_claims_fielding_alignment.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.mlb import claims_fielding_alignment as cfa


def _synthetic_savant(n_per_group: int) -> pd.DataFrame:
    """2 split_groups (L_Standard, R_Infield_shade), n_per_group batted balls
    each, plus one HR each and one non-batted-ball row (should be excluded).
    L_Standard: 3 hits / (n_per_group - 1 outs after removing HR) -- hand-computed below.
    """
    rows = []
    # L_Standard: n_per_group-2 outs, 2 hits (singles), 1 HR, all bb_type set
    for _ in range(n_per_group - 2):
        rows.append({"stand": "L", "if_fielding_alignment": "Standard", "bb_type": "ground_ball",
                      "events": "field_out", "estimated_woba_using_speedangle": 0.05, "game_date": "2023-04-01"})
    rows.append({"stand": "L", "if_fielding_alignment": "Standard", "bb_type": "line_drive",
                 "events": "single", "estimated_woba_using_speedangle": 0.9, "game_date": "2023-04-01"})
    rows.append({"stand": "L", "if_fielding_alignment": "Standard", "bb_type": "line_drive",
                 "events": "single", "estimated_woba_using_speedangle": 0.9, "game_date": "2023-04-01"})
    rows.append({"stand": "L", "if_fielding_alignment": "Standard", "bb_type": "fly_ball",
                 "events": "home_run", "estimated_woba_using_speedangle": 2.0, "game_date": "2023-04-01"})
    # R_Infield shade: n_per_group outs, 0 hits -- BABIP should be 0.0
    for _ in range(n_per_group):
        rows.append({"stand": "R", "if_fielding_alignment": "Infield shade", "bb_type": "ground_ball",
                     "events": "field_out", "estimated_woba_using_speedangle": 0.1, "game_date": "2023-04-02"})
    # a non-batted-ball row (strikeout, bb_type null) -- must be excluded entirely
    rows.append({"stand": "L", "if_fielding_alignment": "Standard", "bb_type": None,
                 "events": "strikeout", "estimated_woba_using_speedangle": None, "game_date": "2023-04-01"})
    return pd.DataFrame(rows)


def test_babip_hand_computed_excludes_hr_from_both_sides(tmp_path):
    df = _synthetic_savant(n_per_group=40)
    claim = cfa.build_babip_claim("2023", df_raw=df, out_dir=tmp_path)
    ranking = {r["split_group"]: r for r in claim["ranking"]}
    # L_Standard: 2 hits / (38 outs + 2 hits) = 2/40 = 0.05 non-HR BIP (HR excluded from denom)
    assert ranking["L_Standard"]["value"] == 0.05
    assert ranking["L_Standard"]["n"] == 40
    # R_Infield_shade: 0 hits / 40 outs = 0.0
    assert ranking["R_Infield_shade"]["value"] == 0.0
    assert ranking["R_Infield_shade"]["n"] == 40


def test_xwoba_contact_includes_hr(tmp_path):
    df = _synthetic_savant(n_per_group=40)
    claim = cfa.build_xwoba_claim("2023", df_raw=df, out_dir=tmp_path)
    ranking = {r["split_group"]: r for r in claim["ranking"]}
    # L_Standard xwoba pop = 38 outs*0.05 + 2 singles*0.9 + 1 HR*2.0, n=41 (HR included, strikeout excluded)
    expected = round((38 * 0.05 + 2 * 0.9 + 1 * 2.0) / 41, 4)
    assert ranking["L_Standard"]["value"] == expected
    assert ranking["L_Standard"]["n"] == 41


def test_n_floor_excludes_thin_groups(tmp_path):
    df = _synthetic_savant(n_per_group=cfa.MIN_N - 1)  # both groups below floor
    claim = cfa.build_babip_claim("2023", df_raw=df, out_dir=tmp_path)
    assert claim["ranking"] == []
    assert claim["n_excluded_below_floor"] == claim["n_considered"] == 2


def test_edge_claimed_false_on_every_row(tmp_path):
    df = _synthetic_savant(n_per_group=40)
    claim = cfa.build_babip_claim("2023", df_raw=df, out_dir=tmp_path)
    assert claim["edge_claimed"] is False
    for row in claim["ranking"]:
        assert claim["edge_claimed"] is False  # claim-level flag covers every ranked row

