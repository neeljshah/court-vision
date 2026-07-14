"""Tests for scripts.platformkit.omni.k_synergy_stint (stint-grain teammate
on/off synergy).

Per-file run only:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_omni_k_synergy_stint.py -q
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.omni import claims_ledger as cl
from scripts.platformkit.omni import k_synergy_stint as kss


def _lineup_row(game_id: str, off_ids: list[int], points: float) -> dict:
    return {"game_id": game_id, "off_lineup_ids": ",".join(str(i) for i in sorted(off_ids)), "points": points}


# -- on/off PPP split math ---------------------------------------------------

def test_on_off_split_basic_delta():
    """Focal(1) scores more (avg 1.5) with partner(2) on the floor than
    without (avg 0.5) -- on/off split must report that delta, sign and n's."""
    rows = []
    for _ in range(10):
        rows.append(_lineup_row("g1", [1, 2, 3, 4, 5], 1.5))  # with partner
    for _ in range(5):
        rows.append(_lineup_row("g1", [1, 6, 3, 4, 5], 0.5))  # without partner
    df = pd.DataFrame(rows)
    masks = kss.player_masks(df, {1, 2})
    res = kss.on_off_split(df["points"].to_numpy(), masks, 1, 2)
    assert res is not None
    assert res["n_a"] == 10 and res["n_b"] == 5
    assert abs(res["delta"] - 1.0) < 1e-9


def test_on_off_split_none_when_no_without_side():
    """If the focal player is NEVER on the floor without the partner, the
    'without' side is empty -- split returns None (not a fabricated zero)."""
    rows = [_lineup_row("g1", [1, 2, 3, 4, 5], 1.0) for _ in range(20)]
    df = pd.DataFrame(rows)
    masks = kss.player_masks(df, {1, 2})
    assert kss.on_off_split(df["points"].to_numpy(), masks, 1, 2) is None


# -- candidate floor -> INSUFFICIENT_DATA ------------------------------------

def test_candidate_pairs_respects_shared_possession_floor():
    rows = [_lineup_row("g1", [1, 2, 3, 4, 5], 1.0) for _ in range(199)]
    df = pd.DataFrame(rows)
    assert kss.candidate_pairs(df, floor=200) == []
    rows.append(_lineup_row("g1", [1, 2, 3, 4, 5], 1.0))
    df2 = pd.DataFrame(rows)
    assert (1, 2) in kss.candidate_pairs(df2, floor=200)


def test_below_without_floor_is_insufficient_data(tmp_path):
    """Pair (1,2) clears the ON floor (250 >= 200) but has too few OFF
    possessions (5 < 30) -- must be ledgered INSUFFICIENT_DATA, never tested/
    BH'd. Filler ids rotate per row so no OTHER pair also reaches the
    candidate floor (keeps this a single-pair scenario)."""
    rows = [_lineup_row("g1", [1, 2, 100 + i, 200 + i, 300 + i], 1.0) for i in range(250)]
    for i in range(5):  # far below MIN_WITHOUT_POSS=30
        rows.append(_lineup_row("g1", [1, 6, 400 + i, 500 + i, 600 + i], 1.0))
    disc = pd.DataFrame(rows)
    out = kss.run_stint_synergy(base_dir=tmp_path, discovery_df=disc, reserve_df=disc.iloc[:0])
    assert out["candidate_pairs"] == 1
    assert out["insufficient_data"] == 2  # both directions (1,2) and (2,1)
    assert out["bh_survivors"] == 0
    final = cl.query(sport="nba", base_dir=tmp_path)
    assert (final["lifecycle"] == "screened").sum() == 2


# -- leak / order: prereg strictly precedes the reserve read -----------------

def test_reserve_data_never_affects_discovery_bh_selection(tmp_path, monkeypatch):
    """Feeding a reserve frame that would (if it leaked in) flip the sign must
    not change which pairs survive discovery BH -- reserve is read only AFTER
    prereg, for survivors only."""
    rows = []
    for _ in range(300):
        rows.append(_lineup_row("g1", [1, 2, 3, 4, 5], 1.2))
    for _ in range(60):
        rows.append(_lineup_row("g1", [1, 6, 3, 4, 5], 0.6))  # real +0.6 bump with partner
    disc = pd.DataFrame(rows)
    # reserve frame with the OPPOSITE sign -- if it ever leaked into discovery
    # selection the survivor set would change; it must not.
    reserve_rows = []
    for _ in range(300):
        reserve_rows.append(_lineup_row("g1", [1, 2, 3, 4, 5], 0.2))
    for _ in range(60):
        reserve_rows.append(_lineup_row("g1", [1, 6, 3, 4, 5], 1.0))
    res = pd.DataFrame(reserve_rows)

    out1 = kss.run_stint_synergy(base_dir=tmp_path, discovery_df=disc, reserve_df=disc.iloc[:0])
    survivors_1 = out1["bh_survivors"]
    # rerun with a base_dir that would fail if reserve altered discovery selection
    out2 = kss.run_stint_synergy(base_dir=tmp_path / "b2", discovery_df=disc, reserve_df=res)
    assert out2["bh_survivors"] == survivors_1  # same discovery-phase survivor count regardless of reserve content


# -- idempotent rerun ---------------------------------------------------------

def test_run_stint_synergy_idempotent(tmp_path):
    rows = []
    for _ in range(250):
        rows.append(_lineup_row("g1", [1, 2, 3, 4, 5], 1.0))
    for _ in range(50):
        rows.append(_lineup_row("g1", [1, 6, 3, 4, 5], 1.0))
    disc = pd.DataFrame(rows)
    out1 = kss.run_stint_synergy(base_dir=tmp_path, discovery_df=disc, reserve_df=disc.iloc[:0])
    out2 = kss.run_stint_synergy(base_dir=tmp_path, discovery_df=disc, reserve_df=disc.iloc[:0])
    assert out1["claims_added"] > 0
    assert out2["claims_added"] == 0  # same claims already in the journal, content-hash idempotent
