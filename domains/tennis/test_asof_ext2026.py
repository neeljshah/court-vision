"""Per-file test for domains.tennis.asof_ext2026.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        domains/tennis/test_asof_ext2026.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.tennis import asof_ext2026 as EXT


def test_matches_ext2026_is_a_clean_concat():
    matches = pd.read_parquet(EXT._MATCHES)
    matches_2026 = pd.read_parquet(EXT._MATCHES_2026)
    ext = pd.read_parquet(EXT.MATCHES_EXT_OUT)
    assert len(ext) == len(matches) + len(matches_2026)
    # 0 event_id overlap -- disjoint namespaces (Sackmann numeric ids vs "espn2026-*").
    assert set(matches["event_id"]) & set(matches_2026["event_id"]) == set()
    # dates strictly increase across the concat boundary (2025-12-17 -> 2026-01-02).
    assert pd.to_datetime(ext["date"].iloc[len(matches) - 1]) < pd.to_datetime(ext["date"].iloc[len(matches)])


def test_pre2026_asof_rows_are_byte_identical_to_production():
    """The whole leak-free claim rests on this: appending 2026 matches AFTER the
    2015-2025 spine must not retroactively change any pre-2026 as-of row."""
    orig_feat = pd.read_parquet("data/domains/tennis/asof_features.parquet")
    ext_feat = pd.read_parquet(EXT.FEATURES_EXT_OUT).iloc[:len(orig_feat)].reset_index(drop=True)
    assert orig_feat.equals(ext_feat)

    orig_ret = pd.read_parquet("data/domains/tennis/asof_return.parquet")
    ext_ret = pd.read_parquet(EXT.RETURN_EXT_OUT).iloc[:len(orig_ret)].reset_index(drop=True)
    assert orig_ret.equals(ext_ret)


def test_2026_rows_get_real_asof_values_where_history_exists():
    feats = pd.read_parquet(EXT.FEATURES_EXT_OUT)
    matches_2026 = pd.read_parquet(EXT._MATCHES_2026)
    f26 = feats[feats["event_id"].isin(matches_2026["event_id"])]
    assert len(f26) == len(matches_2026)
    assert f26["diff_ace_rate_asof"].notna().sum() > 0
