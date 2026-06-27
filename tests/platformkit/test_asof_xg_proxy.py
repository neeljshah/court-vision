"""Guarded real-data smoke + leak-free assertion for domains.soccer.asof_xg_proxy.

Complements tests/platformkit/test_asof_xg_proxy_soccer.py (synthetic golden). This
file adds (a) an explicit no-future-leak assertion on the builder output and (b) a
guarded smoke over the REAL match_stats.parquet that SKIPS cleanly when the local
corpus is absent (data/ is gitignored -> absent on a fresh clone). ACCURACY ONLY;
"xg" is an explicit shots PROXY -- NO market edge claimed, NO true xG on disk.

Run: C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest \
       tests/platformkit/test_asof_xg_proxy.py -q
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from domains.soccer.asof_xg_proxy import _MATCH_STATS_DEFAULT, build_asof_xg_proxy

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REAL_MATCH_STATS = _REPO_ROOT / _MATCH_STATS_DEFAULT


def _synth() -> pd.DataFrame:
    # TA strong (more sot), TB weak; debut rows must be NaN, no future leak.
    return pd.DataFrame({
        "event_id": ["e1", "e2", "e3", "e4"],
        "date": ["2024-08-01", "2024-08-08", "2024-08-15", "2024-08-22"],
        "home_team": ["TA", "TB", "TA", "TB"],
        "away_team": ["TB", "TA", "TB", "TA"],
        "home_shots": [14, 6, 13, 7], "home_sot": [8, 2, 7, 2],
        "away_shots": [5, 12, 6, 11], "away_sot": [1, 6, 2, 5],
    })


def test_leak_free_debut_rows_nan(tmp_path):
    """Every team's first appearance (any slot) must snapshot to NaN (n_prior==0)."""
    dest = build_asof_xg_proxy(match_stats=_synth(), out_path=str(tmp_path / "x.parquet"))
    df = pd.read_parquet(dest)
    for slot in ("home", "away"):
        debut = df[df[f"{slot}_n_prior"] == 0]
        for col in (f"{slot}_xg_for_asof", f"{slot}_xg_against_asof",
                    f"{slot}_xg_supremacy_asof"):
            assert debut[col].isna().all(), f"future-leak: non-NaN {col} on a debut row"
    # Non-debut rows must carry a real value.
    nondebut = df[(df["home_n_prior"] > 0) & (df["away_n_prior"] > 0)]
    assert nondebut["diff_xg_supremacy_asof"].notna().all()


@pytest.mark.skipif(not _REAL_MATCH_STATS.exists(),
                    reason="real soccer match_stats.parquet absent (gitignored corpus)")
def test_real_data_smoke(tmp_path):
    """Guarded smoke: real corpus builds, columns present, debut leak-free, finite cov."""
    ms = pd.read_parquet(_REAL_MATCH_STATS)
    dest = build_asof_xg_proxy(match_stats=ms, out_path=str(tmp_path / "real.parquet"))
    df = pd.read_parquet(dest)

    assert len(df) == len(ms)
    for c in ("diff_xg_for_asof", "diff_xg_against_asof", "diff_xg_supremacy_asof",
              "home_n_prior", "away_n_prior"):
        assert c in df.columns

    # leak-free on real data: debut rows NaN.
    debut = df[df["home_n_prior"] == 0]
    assert debut["home_xg_for_asof"].isna().all()

    # Some real coverage exists once histories accrue.
    covered = df[(df["home_n_prior"] >= 5) & (df["away_n_prior"] >= 5)]
    assert len(covered) > 0
    assert np.isfinite(covered["diff_xg_supremacy_asof"].dropna().to_numpy()).all()
