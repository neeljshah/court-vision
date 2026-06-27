"""Per-file tests for domains.soccer.asof_xg_proxy (shots-based xG-proxy depth).

Drives the full builder on a hand-computed 3-match / 2-team synthetic corpus: the xG
PROXY formula, shared home/away per-team state, the for/against/supremacy diffs, and
leak-freeness (debut -> NaN). Dogfoods asof_common.

Run: C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest \
       tests/platformkit/test_asof_xg_proxy_soccer.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from domains.soccer.asof_xg_proxy import K_OFF, K_SOT, _derive_realized, build_asof_xg_proxy

# m1 TA(home): xg = K_SOT*5 + K_OFF*(10-5); TB(away): K_SOT*2 + K_OFF*(8-2)
_TA_M1_XG = K_SOT * 5 + K_OFF * 5
_TB_M1_XG = K_SOT * 2 + K_OFF * 6


def _match_stats() -> pd.DataFrame:
    return pd.DataFrame({
        "event_id": ["m1", "m2", "m3"],
        "date": ["2024-08-01", "2024-08-08", "2024-08-15"],
        "home_team": ["TA", "TB", "TA"],
        "away_team": ["TB", "TA", "TB"],
        "home_shots": [10, 12, 9], "home_sot": [5, 6, 4],
        "away_shots": [8, 7, 10], "away_sot": [2, 3, 5],
    })


def test_xg_formula():
    r = _derive_realized(_match_stats()).set_index("event_id")
    assert r.loc["m1", "home_xg_for"] == pytest.approx(_TA_M1_XG)
    assert r.loc["m1", "away_xg_for"] == pytest.approx(_TB_M1_XG)
    # against is the opponent's for (symmetric)
    assert r.loc["m1", "home_xg_against"] == pytest.approx(_TB_M1_XG)
    assert r.loc["m1", "away_xg_against"] == pytest.approx(_TA_M1_XG)


def test_build_shared_state_diffs_and_leak_free(tmp_path):
    dest = build_asof_xg_proxy(match_stats=_match_stats(),
                               out_path=str(tmp_path / "xg.parquet"))
    df = pd.read_parquet(dest).set_index("event_id")

    # m1: both teams debut -> NaN
    assert np.isnan(df.loc["m1", "diff_xg_for_asof"])
    assert df.loc["m1", "home_n_prior"] == 0

    # m2: TA(away) prior xg_for = TA m1 (home) = _TA_M1_XG; TB(home) prior = TB m1 (away).
    assert df.loc["m2", "away_xg_for_asof"] == pytest.approx(_TA_M1_XG)
    assert df.loc["m2", "home_xg_for_asof"] == pytest.approx(_TB_M1_XG)
    assert df.loc["m2", "diff_xg_for_asof"] == pytest.approx(_TB_M1_XG - _TA_M1_XG)
    # supremacy = xg_for - xg_against; TB home: _TB - _TA ; TA away: _TA - _TB
    home_sup = _TB_M1_XG - _TA_M1_XG
    away_sup = _TA_M1_XG - _TB_M1_XG
    assert df.loc["m2", "diff_xg_supremacy_asof"] == pytest.approx(home_sup - away_sup)


def test_output_columns_present(tmp_path):
    dest = build_asof_xg_proxy(match_stats=_match_stats(),
                               out_path=str(tmp_path / "xg.parquet"))
    cols = set(pd.read_parquet(dest).columns)
    for c in ("diff_xg_for_asof", "diff_xg_against_asof", "diff_xg_supremacy_asof",
              "event_id", "home_n_prior", "away_n_prior"):
        assert c in cols
