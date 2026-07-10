"""python -m pytest domains/mlb/pitch_engine/test_bullpen_v3.py -q"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.mlb.pitch_engine.bullpen_v3 import PitcherQualityTier, RelieverPAv3, N_PA, N_TIER
from domains.mlb.pitch_engine.pa_chain import _PA_IX


def _relief_frame(n: int = 45):
    """3 relievers, distinct K-rates, all in the SAME (inn_bucket=1, lead_state=2)
    cell (>= _REL_MIN=40 rows each -> exercises the full cell path)."""
    rows = []
    ab = 1
    for pitcher, krate in ((100, 1.0), (200, 1.0 / 3), (300, 0.0)):
        n_k = round(n * krate)
        for i in range(n):
            evt = "K" if i < n_k else "OUT"
            rows.append(dict(pitcher=pitcher, batter=900 + i, pa_evt=evt, is_relief=True,
                             inn_bucket=1, lead_state=2, game_pk=1, at_bat_number=ab))
            ab += 1
    return pd.DataFrame(rows)


def test_pitcher_quality_tier_orders_by_k_rate():
    pt = PitcherQualityTier.fit(_relief_frame())
    assert pt.tier(300) == 0     # low K
    assert pt.tier(200) == 1     # mid K
    assert pt.tier(100) == 2     # high K
    assert pt.tier(999999) == 1  # unknown pitcher backs off to mid


def test_reliever_pa_v3_stratifies_by_tier():
    pa = _relief_frame()
    pt = PitcherQualityTier.fit(pa)
    rp = RelieverPAv3.fit(pa, pt)
    k_ix = _PA_IX["K"]
    v_hi = rp.probs(1, 2, 2)   # tier2 = high-K pitcher's own cell
    v_lo = rp.probs(1, 2, 0)   # tier0 = low-K pitcher's own cell
    assert v_hi.shape == (N_PA,)
    assert abs(v_hi.sum() - 1.0) < 1e-9
    assert v_hi[k_ix] > v_lo[k_ix]

    mixed = rp.mixed_probs(1, 2)
    assert abs(mixed.sum() - 1.0) < 1e-9
    # mixed sits between the tier extremes (weighted average of 3 tiers)
    assert v_lo[k_ix] <= mixed[k_ix] <= v_hi[k_ix]

    m = rp.bucket_lead_matrix()
    assert m.shape == (4, 3, N_PA)
    assert np.allclose(m.sum(axis=2), 1.0)


def test_backoff_for_unseen_cell():
    pa = _relief_frame()
    pt = PitcherQualityTier.fit(pa)
    rp = RelieverPAv3.fit(pa, pt)
    v = rp.probs(3, 0, 1)      # bucket/lead/tier never seen -> backs off, still valid
    assert abs(v.sum() - 1.0) < 1e-9
    assert (v >= 0).all()
