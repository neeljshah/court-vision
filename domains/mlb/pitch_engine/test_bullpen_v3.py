"""python -m pytest domains/mlb/pitch_engine/test_bullpen_v3.py -q"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.mlb.pitch_engine.bullpen_v3 import (PitcherQualityTier, TeamBullpenTier,
                                                  RelieverPAv3, pitcher_team, N_PA, N_TIER)
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


def _team_relief_frame(n: int = 155):
    """2 teams, distinct K-rates, own reliever pool each (>= _MIN_TEAM_PA=150
    rows/team) so TeamBullpenTier can trust both team cells."""
    rows = []
    ab = 1
    for pitcher, home, away, topbot, krate in (
            (100, "AAA", "BBB", "Top", 1.0),      # AAA pitches (home, Top) -- high K
            (200, "CCC", "DDD", "Bot", 0.0)):     # DDD pitches (away, Bot) -- low K
        n_k = round(n * krate)
        for i in range(n):
            evt = "K" if i < n_k else "OUT"
            rows.append(dict(pitcher=pitcher, batter=900 + i, pa_evt=evt, is_relief=True,
                             inn_bucket=1, lead_state=2, game_pk=1, at_bat_number=ab,
                             home_team=home, away_team=away, inning_topbot=topbot))
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


def test_pitcher_team_derives_from_home_away_topbot():
    pa = _team_relief_frame()
    teams = pitcher_team(pa)
    top = pa["inning_topbot"].to_numpy() == "Top"
    assert (teams[top] == "AAA").all()     # Top half -> home team pitches
    assert (teams[~top] == "DDD").all()    # Bot half -> away team pitches


def test_team_bullpen_tier_orders_by_k_rate():
    tt = TeamBullpenTier.fit(_team_relief_frame())
    assert tt.tier("AAA") == 2   # all-K team -> high tier
    assert tt.tier("DDD") == 0   # all-OUT team -> low tier
    assert tt.tier("ZZZ") == 1   # unknown team backs off to mid


def test_reliever_pa_v3_team_tier_param_changes_composition():
    pa = _team_relief_frame()
    pt = PitcherQualityTier.fit(pa)
    tt = TeamBullpenTier.fit(pa)
    rp_default = RelieverPAv3.fit(pa, pt)                    # default: pitcher tier
    rp_team = RelieverPAv3.fit(pa, pt, team_tiers=tt)        # candidate: team tier
    k_ix = _PA_IX["K"]
    # both are valid distributions; the team-tier run must actually route PAs
    # through the team axis (AAA/high-K cell present at tier 2, DDD/low-K at 0)
    assert abs(rp_team.probs(1, 2, 2).sum() - 1.0) < 1e-9
    assert rp_team.probs(1, 2, 2)[k_ix] > rp_team.probs(1, 2, 0)[k_ix]
    assert rp_default.bucket_lead_matrix().shape == rp_team.bucket_lead_matrix().shape
