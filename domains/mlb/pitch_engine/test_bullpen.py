"""python -m pytest domains/mlb/pitch_engine/test_bullpen.py -q"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.mlb.pitch_engine import bullpen as bp


class _Tiers:
    def tier(self, batter, class_ix):
        return int(batter) % 3


def _pa_frame():
    """1 game: home SP=100 (inn1-6) then RP=200 (7-9); away SP=300 (inn1-7) then
    RP=400 (8-9). One PA per half-inning."""
    rows = []
    ab = 1
    for inn in range(1, 10):
        # Top: away bats, home pitches
        hp = 100 if inn <= 6 else 200
        rows.append(dict(game_pk=1, inning=inn, inning_topbot="Top", at_bat_number=ab,
                         pitcher=hp, batter=10 + (inn % 9), pa_evt="OUT",
                         home_score=2, away_score=0, game_date="2024-05-01")); ab += 1
        # Bot: home bats, away pitches
        apn = 300 if inn <= 7 else 400
        rows.append(dict(game_pk=1, inning=inn, inning_topbot="Bot", at_bat_number=ab,
                         pitcher=apn, batter=20 + (inn % 9), pa_evt="1B",
                         home_score=2, away_score=0, game_date="2024-05-01")); ab += 1
    return pd.DataFrame(rows)


def test_mark_context_flags_relievers():
    pa = bp.mark_context(_pa_frame())
    rel = pa[pa["is_relief"]]
    assert set(rel["pitcher"]) == {200, 400}
    # home pitcher (Top) with fld_score=2>bat_score=0 -> pitcher leading (2)
    top = pa[pa["inning_topbot"] == "Top"]
    assert (top["lead_state"] == 2).all()


def test_removal_hazard_and_survival():
    m = bp.RemovalModel.fit(_pa_frame())
    h = m._h
    assert h.shape == (bp.N_INN, bp.N_LEAD)
    assert ((h >= 0) & (h <= 1)).all()
    assert (h[:bp.MIN_REMOVAL_INN] == 0).all()          # early-inning gate
    # cumulative removed_by non-decreasing in inning
    prev = -1.0
    for k in range(bp.N_INN):
        rb = m.removed_by(k, 2)
        assert 0.0 <= rb <= 1.0 and rb >= prev - 1e-9
        prev = rb


def test_reliever_pa_normalized():
    pa = bp.mark_context(_pa_frame())
    cad = bp.reliever_cadence(pa)
    rp = bp.RelieverPA.fit(pa, _Tiers(), cad)
    v = rp.probs(3, 2, 1, 1)
    assert v.shape == (bp.N_PA,)
    assert abs(v.sum() - 1.0) < 1e-9
    sm = rp.slot_matrix([10, 11, 12, 13, 14, 15, 16, 17, 18], _Tiers(), 0.7)
    assert sm.shape == (bp.N_BUCKET, bp.N_LEAD, 9, bp.N_PA)
    assert np.allclose(sm.sum(axis=3), 1.0)


def test_cadence_counts_back_to_back():
    pa = _pa_frame()
    pa2 = pa.copy()
    pa2["game_pk"] = 2
    pa2["game_date"] = "2024-05-02"                      # reliever 200 pitches next day
    cad = bp.reliever_cadence(pd.concat([pa, pa2], ignore_index=True))
    r200 = cad[(cad["pitcher"] == 200) & (cad["game_pk"] == 2)]
    assert float(r200["apps_last_3d"].iloc[0]) == 1.0    # one prior app in trailing 3d


def test_bullpen_freshness_fraction():
    pa = bp.mark_context(_pa_frame())
    cad = bp.reliever_cadence(pa)
    fr = bp.bullpen_freshness(pa, cad)
    assert fr[(1, "Top")] == 1.0                         # RP 200 fresh (first app)
    assert 0.0 <= fr[(1, "Bot")] <= 1.0
