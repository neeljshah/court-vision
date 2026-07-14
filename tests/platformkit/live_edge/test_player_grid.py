"""Per-file test for scripts.platformkit.live_edge.player_grid.*

Uses tiny synthetic frames -- never reads the real (large) parquets, per
per-file-test discipline. Covers: attach_scorer's exact-match join key,
explode_on_floor's on-floor `scored` assignment, the per-player-complement
Welch test (TESTED + INSUFFICIENT_DATA branches), and claim_for_row's
lifecycle gating.
"""
import numpy as np
import pandas as pd

from scripts.platformkit.live_edge.player_grid import player_grid as pg
from scripts.platformkit.live_edge.player_grid import player_mine as pm


def _tiny_tagged_df():
    # 4 possessions, game "g1", season 2024-25, 2 offensive lineup slots each.
    return pd.DataFrame({
        "game_id": ["g1", "g1", "g1", "g1"],
        "season": ["2024-25"] * 4,
        "off_lineup_ids": ["1,2", "1,2", "1,2", "1,2"],
        "def_lineup_ids": ["3,4", "3,4", "3,4", "3,4"],
        "lineup_available": [True, True, True, True],
        "margin_bucket": ["tied", "tied", "up1to9", "up1to9"],
    })


def _tiny_scorer_source():
    scorer_2024 = pd.DataFrame({
        "game_id": ["g1", "g1", "g1", "g1"],
        "poss_idx": [0, 1, 2, 3],
        "scorer_player_id": [1.0, np.nan, 2.0, 1.0],
        "scorer_points": [2, 0, 3, 2],
    })
    return {"2024-25": scorer_2024}


def test_attach_scorer_join_key():
    tagged = _tiny_tagged_df()
    out = pg.attach_scorer(tagged, scorer_source=_tiny_scorer_source())
    assert list(out["poss_idx"]) == [0, 1, 2, 3]
    assert out.loc[out["poss_idx"] == 2, "scorer_points"].iloc[0] == 3


def test_explode_on_floor_scored_assignment():
    tagged = _tiny_tagged_df()
    scored_df = pg.attach_scorer(tagged, scorer_source=_tiny_scorer_source())
    long = pg.explode_on_floor(scored_df)
    # 4 possessions x 2 on-floor players = 8 rows.
    assert len(long) == 8
    p1 = long[long["player_id"] == "1"].sort_values("poss_idx")
    assert list(p1["scored"]) == [2.0, 0.0, 0.0, 2.0]
    p2 = long[long["player_id"] == "2"].sort_values("poss_idx")
    assert list(p2["scored"]) == [0.0, 0.0, 3.0, 0.0]


def test_welch_vs_player_complement_and_claim_gating():
    # Player "1" scores heavily in "tied", never in "up1to9" -- big within-
    # player delta, big n on both sides -> should be TESTED, not INSUFFICIENT.
    rows = []
    for i in range(40):
        rows.append({"player_id": "1", "margin_bucket": "tied", "scored": 3.0 if i % 2 else 2.0})
    for i in range(40):
        rows.append({"player_id": "1", "margin_bucket": "up1to9", "scored": 0.0 if i % 2 else 1.0})
    df = pd.DataFrame(rows)
    g = pm.welch_vs_player_complement(df, ["margin_bucket"])
    tied_row = g[g["margin_bucket"] == "tied"].iloc[0].to_dict()
    assert tied_row["n"] == 40 and tied_row["comp_n"] == 40
    assert tied_row["delta"] > 1.9  # scores ~2 more per possession than complement
    tied_row["p_adj"] = tied_row["p"]  # BH pass-through for this unit test
    claim, escalate = pm.claim_for_row(
        tied_row, ["margin_bucket"], "player_margin", True, "2024-25", "unit-test")
    assert claim["effect"]["verdict"] == "TESTED"
    assert escalate is True
    assert claim["topic"] == "player_cell.player_margin"
    assert "situation" not in claim["topic"]  # must not collide with B4's claim filter


def test_claim_for_row_insufficient_data_floor():
    rec = {"player_id": "9", "margin_bucket": "tied", "n": 5, "comp_n": 200,
           "delta": 1.0, "p_adj": 0.001}
    claim, escalate = pm.claim_for_row(rec, ["margin_bucket"], "player_margin", True, "2024-25", "unit-test")
    assert claim["effect"]["verdict"] == "INSUFFICIENT_DATA"
    assert escalate is False


if __name__ == "__main__":
    test_attach_scorer_join_key()
    test_explode_on_floor_scored_assignment()
    test_welch_vs_player_complement_and_claim_gating()
    test_claim_for_row_insufficient_data_floor()
    print("all player_grid tests passed")
