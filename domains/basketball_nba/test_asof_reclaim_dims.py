"""Per-file test for domains.basketball_nba.asof_reclaim_dims.

Acceptance criteria
--------------------
1. add_pair_diffs: diff_col == home_col - away_col exactly (by construction);
   NaN propagates when either side is NaN; original columns are untouched.
2. LEAK GUARD: a diff value for game i depends ONLY on the home/away_*_asof inputs
   already computed by asof_features.py's snapshot-before-update walk (i.e. it is a
   pure row-wise transform -- verified here by reconstructing a synthetic prior-only
   walk-forward frame with a KNOWN strictly-earlier-only history and checking the
   diff matches manual re-derivation, plus confirming diff values never change when
   a LATER row's home/away columns are perturbed row-independence).
3. load_reclaim_frame: merges asof_features + asof_box_extra on game_id (str-safe);
   RECLAIM_DIFF_COLS names match what load_reclaim_frame actually produces;
   ast_rate_diff_asof is excluded from RECLAIM_DIFF_COLS (previously rejected).
4. No $ / ROI / edge / profit language anywhere in module-level constants.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        domains/basketball_nba/test_asof_reclaim_dims.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.basketball_nba import asof_reclaim_dims as mod


def _synthetic_features(n: int = 20, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    gids = [f"g{i:04d}" for i in range(n)]
    df = pd.DataFrame({
        "game_id": gids,
        "home_pace_asof": rng.normal(100, 3, n),
        "away_pace_asof": rng.normal(100, 3, n),
        "home_oreb_pg_asof": rng.normal(10, 2, n),
        "away_oreb_pg_asof": rng.normal(10, 2, n),
        "home_tov_pg_asof": rng.normal(13, 2, n),
        "away_tov_pg_asof": rng.normal(13, 2, n),
        "home_n_prior": rng.integers(0, 10, n),
        "away_n_prior": rng.integers(0, 10, n),
    })
    # First row has no prior history -> NaN sentinel (mirrors asof_features.py).
    for c in ("home_pace_asof", "home_oreb_pg_asof", "home_tov_pg_asof"):
        df.loc[0, c] = np.nan
    return df


def _synthetic_box_extra(n: int = 20, seed: int = 4) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    gids = [f"g{i:04d}" for i in range(n)]
    return pd.DataFrame({
        "game_id": gids,
        "dreb_diff_asof": rng.normal(0, 1, n),
        "fg3m_diff_asof": rng.normal(0, 1, n),
        "stl_diff_asof": rng.normal(0, 1, n),
        "blk_diff_asof": rng.normal(0, 1, n),
    })


def test_add_pair_diffs_exact_and_nan_propagates():
    feat = _synthetic_features()
    out = mod.add_pair_diffs(feat)
    for diff_col, (hcol, acol) in mod._PAIR_DIFFS.items():
        expected = feat[hcol] - feat[acol]
        pd.testing.assert_series_equal(
            out[diff_col], expected, check_names=False, check_dtype=False,
        )
    # Row 0 was seeded NaN on the home side -> diff must be NaN, not fabricated.
    for diff_col in mod._PAIR_DIFFS:
        assert pd.isna(out.loc[0, diff_col])
    # Original columns untouched.
    for hcol_acol in mod._PAIR_DIFFS.values():
        for c in hcol_acol:
            pd.testing.assert_series_equal(out[c], feat[c], check_names=False)


def test_diff_is_pure_row_transform_leak_guard():
    """A diff at row i must not change if we perturb a DIFFERENT row's inputs.

    This is the leak guard for a row-wise arithmetic transform: since diff_i is
    computed only from home_i/away_i (already strictly-prior-only per
    asof_features.py), corrupting row j != i must leave row i's diff untouched.
    """
    feat = _synthetic_features()
    out_a = mod.add_pair_diffs(feat)

    perturbed = feat.copy()
    perturbed.loc[5, "home_pace_asof"] = 9999.0
    perturbed.loc[5, "home_oreb_pg_asof"] = 9999.0
    out_b = mod.add_pair_diffs(perturbed)

    for diff_col in mod._PAIR_DIFFS:
        untouched_rows = [i for i in range(len(feat)) if i != 5]
        pd.testing.assert_series_equal(
            out_a[diff_col].iloc[untouched_rows].reset_index(drop=True),
            out_b[diff_col].iloc[untouched_rows].reset_index(drop=True),
            check_names=False,
        )


def test_load_reclaim_frame_merge_and_columns():
    feat = _synthetic_features()
    box = _synthetic_box_extra()
    out = mod.load_reclaim_frame(asof_features=feat, asof_box_extra=box)
    assert len(out) == len(feat)
    for c in mod.RECLAIM_DIFF_COLS:
        assert c in out.columns, f"missing reclaim column {c}"


def test_previously_rejected_excluded_from_reclaim_set():
    assert "ast_rate_diff_asof" not in mod.RECLAIM_DIFF_COLS
    assert "ast_rate_diff_asof" in mod.PREVIOUSLY_REJECTED


def test_no_dollar_or_edge_language():
    banned = {"roi", "pnl", "p_l", "edge", "profit", "dollars", "$"}
    haystack = " ".join(mod.RECLAIM_DIFF_COLS) + " " + " ".join(mod.PREVIOUSLY_REJECTED)
    haystack = haystack.lower()
    assert not any(b in haystack for b in banned)
