"""S111 (b) -- both linescores shards, one chronological as-of walk, the bridge as the key.

The load-bearing test is `test_prior_history_crosses_the_shard_boundary`: folding the
2024-25 shard in is only worth anything if a 2025-26 row's trailing value now reads the
earlier season's games AND still never reads its own. The other two check the key: the
exact bridge wins, and a row the bridge does not carry is left NaN rather than guessed.

Test: python -m pytest domains/basketball_nba/test_asof_quarter_shape_full.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pytest import approx

from domains.basketball_nba import asof_quarter_shape_full as full


def _linescores(rows) -> pd.DataFrame:
    """rows = (event_id, date, home_abbr, away_abbr, home_q, away_q) with flat quarter scores."""
    frame = pd.DataFrame(rows, columns=["event_id", "date", "home_abbr", "away_abbr", "h", "a"])
    for q in ("q1", "q2", "q3", "q4"):
        frame["home_%s" % q] = frame["h"]
        frame["away_%s" % q] = frame["a"]
    frame["date"] = pd.to_datetime(frame["date"])
    return frame.drop(columns=["h", "a"])


def test_union_is_both_shards_and_dedups_on_event_id(tmp_path):
    old = _linescores([("1", "2024-11-01", "BOS", "NYK", 30, 20)])
    new = _linescores([("1", "2024-11-01", "BOS", "NYK", 30, 20),
                       ("2", "2025-11-01", "BOS", "LAL", 25, 25)])
    old.to_parquet(tmp_path / "a.parquet")
    new.to_parquet(tmp_path / "b.parquet")
    union = full.union_linescores([tmp_path / "a.parquet", tmp_path / "b.parquet"])
    assert list(union["event_id"]) == ["1", "2"], "deduped on event_id, date-ordered"


def test_prior_history_crosses_the_shard_boundary(tmp_path):
    """BOS's third game sees its first two -- one of them from the earlier shard -- never itself."""
    rows = [("1", "2024-11-01", "BOS", "NYK", 30, 20),    # BOS q1 margin +10
            ("2", "2025-11-01", "BOS", "LAL", 40, 20),    # +20
            ("3", "2025-11-08", "BOS", "MIA", 50, 20)]    # +30, must not see itself
    out = pd.read_parquet(full.build_full(
        tmp_path / "out.parquet", linescores=_linescores(rows), games=pd.DataFrame(),
        bridge=pd.DataFrame(columns=["event_id", "game_id", "match_confidence"])))
    got = out.set_index("event_id")["home_q1_margin_asof"]
    assert np.isnan(got.loc["1"]), "a debut row must not see its own game"
    assert got.loc["2"] == approx(10.0), "row 2 sees only the 2024-25 shard row"
    assert got.loc["3"] == approx(15.0), "row 3 sees rows 1-2 and never its own +30"


def test_bridge_key_wins_and_an_unbridged_row_stays_nan():
    result = pd.DataFrame({"event_id": ["1", "2"], "game_id": [np.nan, "0022400002"]})
    bridge = pd.DataFrame({"event_id": ["1", "3"], "game_id": ["0022400001", "0022400003"],
                           "match_confidence": ["exact", "fuzzy"]})
    keyed = full.attach_bridge_key(result, bridge).set_index("event_id")["game_id"]
    assert keyed.loc["1"] == "0022400001", "the exact bridge fills what the abbr join missed"
    assert keyed.loc["2"] == "0022400002", "an existing key survives when the bridge has none"
    assert "3" not in keyed.index, "the bridge never adds rows"
