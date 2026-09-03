"""S111 (a) -- the WTA siblings run the SAME builders under the SAME strictly-before rule.

The load-bearing test is `test_strictly_before_on_a_synthetic_spine`: the whole point of a
sibling table is that it is as-of, so a match on date D must see only matches with date < D.
The rest are construct checks on the two things the sibling wiring actually changes: which
sidecar rows it reads, and which raw glob the meta builder walks.

Test: python -m pytest domains/tennis/test_asof_wta_siblings.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pytest import approx

from domains.tennis import asof_meta, asof_wta_siblings
from domains.tennis.asof_features import build_asof_features


def _spine(dates, pairs) -> pd.DataFrame:
    return pd.DataFrame({
        "event_id": ["%s-wta-T-%d" % (d.replace("-", ""), i) for i, d in enumerate(dates)],
        "date": pd.to_datetime(dates), "tour": "wta", "tourney_id": "T",
        "round": "R32", "match_num": list(range(len(dates))),
        "p1_id": [p[0] for p in pairs], "p2_id": [p[1] for p in pairs]})


def test_strictly_before_on_a_synthetic_spine(tmp_path):
    """Player 1 plays three matches; each row's as-of is the mean of the EARLIER ones only."""
    spine = _spine(["2020-01-01", "2020-01-08", "2020-01-15"], [(1, 2), (1, 3), (1, 4)])
    stats = pd.DataFrame({"event_id": spine["event_id"],
                          "p1_ace_rate": [0.10, 0.20, 0.30], "p2_ace_rate": [0.5, 0.5, 0.5]})
    out = pd.read_parquet(build_asof_features(match_stats=stats, matches=spine,
                                              out_path=str(tmp_path / "f.parquet")))
    got = out.set_index("event_id")["p1_ace_rate_asof"]
    assert np.isnan(got.iloc[0]), "a debut row must not see its own match"
    assert got.iloc[1] == approx(0.10), "row 2 sees only row 1"
    assert got.iloc[2] == approx(0.15), "row 3 sees rows 1-2 and never its own 0.30"
    assert list(out["p1_n_prior"]) == [0, 1, 2]


def test_wta_match_stats_keeps_only_the_wta_tagged_rows():
    mixed = pd.DataFrame({"event_id": ["20200101-atp-a-1", "20200101-wta-b-1"],
                          "p1_ace_rate": [0.1, 0.2]})
    assert list(asof_wta_siblings.wta_match_stats(mixed)["event_id"]) == ["20200101-wta-b-1"]


def test_meta_pattern_is_additive_and_selects_the_wta_raw_glob(tmp_path):
    """The default glob is untouched; the WTA glob reads the WTA year CSVs and only those."""
    for name, ident in (("atp_matches_2020.csv", "A"), ("wta_matches_2020.csv", "W")):
        pd.DataFrame({"winner_id": [1], "loser_id": [2], "tourney_id": [ident],
                      "match_num": [1]}).to_csv(tmp_path / name, index=False)
    assert list(asof_meta._read_raw_year_csvs(str(tmp_path))["tourney_id"]) == ["A"]
    wta = asof_meta._read_raw_year_csvs(str(tmp_path), "wta_matches_*.csv")
    assert list(wta["tourney_id"]) == ["W"]
