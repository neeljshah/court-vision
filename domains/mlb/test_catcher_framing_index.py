"""Per-file tests for catcher_framing_index (program v2 build rank 1,
catcher arm). Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    domains/mlb/test_catcher_framing_index.py -q

Acceptance criteria:
  1. derive_out_of_zone uses `type`+`zone` (never `des`) to classify
     is_strike (called-or-swung-or-foul, NOT called-strike-only -- see
     module CORRECTNESS FIX docstring) / out-of-zone.
  2. build_catcher_index applies the min_ooz_called floor correctly and
     reports n_considered / n_excluded honestly.
  3. shuffle_fielder2_within_game preserves game_pk group membership + row
     count, only permutes catcher identity within each game.
  4. Real on-disk corpus smoke test: index builds, is non-empty, and every
     row's rate is a valid probability.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.mlb import catcher_framing_index as cfi


def _fixture_called_pitches() -> pd.DataFrame:
    # 2 catchers, catcher 1 gets 2 out-of-zone calls (1 strike, 1 ball),
    # catcher 2 gets 1 out-of-zone ball + 1 in-zone strike (zone<11, excluded).
    return pd.DataFrame({
        "game_pk": [1, 1, 1, 2],
        "type": ["S", "B", "B", "S"],
        "zone": [11, 13, 12, 5],
        "fielder_2": [100, 100, 200, 200],
        "des": ["x strikes out swinging.", None, None, None],  # des present but MUST be ignored
        "plate_x": [0.9, -0.95, 1.0, 0.1],
        "plate_z": [2.5, 2.4, 2.6, 2.5],
        "sz_top": [3.4, 3.4, 3.4, 3.4],
        "sz_bot": [1.5, 1.5, 1.5, 1.5],
    })


def test_derive_out_of_zone_uses_type_and_zone_not_des():
    df = _fixture_called_pitches()
    derived = cfi.derive_out_of_zone(df)
    # zone>=11 -> out_of_zone True for rows 0,1,2; row 3 zone=5 -> False
    assert list(derived["out_of_zone"]) == [True, True, True, False]
    # is_strike derived from type=='S' (called-or-swung-or-foul, NOT called-strike-only),
    # independent of des content/nullness
    assert list(derived["is_strike"]) == [1, 0, 0, 1]


def test_build_catcher_index_applies_floor_and_reports_honestly():
    df = _fixture_called_pitches()
    qualifiers, report = cfi.build_catcher_index(called=df, min_ooz_called=2)
    # catcher 100: 2 out-of-zone called-or-swung pitches (1 strike, 1 ball) -> qualifies
    # catcher 200: 1 out-of-zone pitch (the zone=5 row is NOT out-of-zone) -> excluded
    assert report["n_catchers_considered"] == 2
    assert report["n_catchers_excluded_below_floor"] == 1
    assert report["metric_is_NOT_a_called_strike_or_framing_rate"] is True
    assert list(qualifiers["catcher_id"]) == [100]
    assert qualifiers.iloc[0]["ooz_strike_rate"] == 0.5


def test_shuffle_fielder2_within_game_preserves_group_membership():
    df = _fixture_called_pitches()
    shuffled = cfi.shuffle_fielder2_within_game(df, seed=1)
    assert len(shuffled) == len(df)
    # game_pk 1 rows must still only contain ids drawn from game_pk 1's original set
    orig_game1_ids = set(df.loc[df["game_pk"] == 1, "fielder_2"])
    shuf_game1_ids = set(shuffled.loc[shuffled["game_pk"] == 1, "fielder_2"])
    assert shuf_game1_ids.issubset(orig_game1_ids)
    # game_pk column itself is untouched
    assert list(shuffled["game_pk"]) == list(df["game_pk"])


def test_real_corpus_index_builds_and_rates_are_valid_probabilities():
    """Smoke test against the REAL on-disk statcast_fuller corpus -- proves the
    index actually builds end-to-end, not just against a synthetic fixture."""
    qualifiers, report = cfi.build_catcher_index()
    assert len(qualifiers) > 0
    assert report["n_qualifying_catchers"] == len(qualifiers)
    assert qualifiers["ooz_strike_rate"].between(0, 1).all()
    assert report["zone_vs_geometric_agreement_frac"] > 0.9
    assert report["descriptive_only"] is True
    assert report["edge_claimed"] is False
    assert report["metric_is_NOT_a_called_strike_or_framing_rate"] is True
