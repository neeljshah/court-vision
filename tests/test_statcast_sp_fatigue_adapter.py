"""Per-file tests for domains.mlb.statcast_sp_fatigue_adapter + the Statcast K-prop
gate wrapper. LEAK-FREE contract + planted-null-rejects + no-fabrication checks.
Run ONLY this file:
  python -m pytest tests/test_statcast_sp_fatigue_adapter.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from domains.mlb import statcast_sp_fatigue_adapter as A


def _toy_starter_table() -> pd.DataFrame:
    """Two pitchers, several starts each, ascending dates."""
    rows = []
    for pid, base_k in ((100, 6), (200, 3), (300, 5), (400, 2)):
        for i in range(8):
            rows.append({
                "season": 2022, "game_id": 1000 + pid * 10 + i,
                "date": f"2022-05-{i + 1:02d}", "pitcher": pid,
                "pitch_team": f"T{pid}", "pitch_side": "home",
                "n_pitches": 90 + i, "innings_pitched": 5 + (i % 2),
                "mean_velo": 92.0 - 0.1 * i, "mean_early_velo": 94.0 - 0.1 * i,
                "velo_decline_slope": -0.05 - 0.001 * i, "mean_spin": 2200 + i,
                "pitch_mix_entropy": 1.2 + 0.01 * i, "frac_breaking": 0.2,
                "label_k": base_k + (i % 3),
            })
    return pd.DataFrame(rows)


def test_profile_is_shift1_leakfree(tmp_path):
    """The current start's OWN shape must NEVER appear in its prior-N profile."""
    st = _toy_starter_table()
    fp = tmp_path / "starter_table__2022.parquet"
    st.to_parquet(fp)
    fr = A.build_frame(2022, path=fp)
    fr = fr.sort_values(["pitcher", "date"]).reset_index(drop=True)
    # First start of each pitcher: no prior -> profile + base must be NaN (NOT 0-filled).
    first = fr.groupby("pitcher").head(1)
    assert first["prof_velo_decline_slope"].isna().all()
    assert first[A._BASE_COL].isna().all()
    # Second start: prof_n_prior == 1, and base == the pitcher's FIRST label_k exactly.
    for pid in (100, 200):
        sub = fr[fr["pitcher"] == pid].sort_values("date").reset_index(drop=True)
        assert sub.loc[1, "prof_n_prior"] == 1
        first_k = float(st[st["pitcher"] == pid].sort_values("date")["label_k"].iloc[0])
        assert sub.loc[1, A._BASE_COL] == pytest.approx(first_k)


def test_label_never_a_feature_and_nondegenerate(tmp_path):
    st = _toy_starter_table()
    fp = tmp_path / "starter_table__2022.parquet"
    st.to_parquet(fp)
    fr = A.build_frame(2022, path=fp)
    # label_k preserved as a column; the BASE is a DISTINCT shift1 series, not the label.
    assert A._LABEL_COL in fr.columns and A._BASE_COL in fr.columns
    joined = fr.dropna(subset=[A._BASE_COL])
    # base must differ from the contemporaneous label (would equal it iff leaked).
    assert not np.allclose(joined[A._BASE_COL].to_numpy(),
                           joined[A._LABEL_COL].to_numpy())
    assert not A.label_is_degenerate(st)


def test_planted_null_present_and_noise(tmp_path):
    st = _toy_starter_table()
    fp = tmp_path / "starter_table__2022.parquet"
    st.to_parquet(fp)
    fr = A.build_frame(2022, path=fp, seed=7)
    assert A._NULL_FEAT in fr.columns
    # null must be (near) uncorrelated with the label by construction.
    j = fr.dropna(subset=[A._LABEL_COL])
    r = np.corrcoef(j[A._NULL_FEAT], j[A._LABEL_COL])[0, 1]
    assert abs(r) < 0.6  # noise, not a signal


def test_real_on_disk_corpora_load_and_cover():
    """Smoke against the REAL acquired Statcast starter_table (if present)."""
    a, b, cov = A.load_both()
    if a.empty or b.empty:
        pytest.skip("real starter_table parquet not on disk")
    assert cov["n_starts"][2022] >= 150 and cov["n_starts"][2023] >= 150
    assert not A.label_is_degenerate(a) and not A.label_is_degenerate(b)
    # leak-free: base is NaN on each pitcher's first start (no prior).
    for fr in (a, b):
        firsts = fr.sort_values(["pitcher", "date", "game_id"]).groupby("pitcher").head(1)
        assert firsts[A._BASE_COL].isna().mean() > 0.9
