"""tests.tennis.test_asof_features — offline leak-free tests for the tennis
AS-OF serve/return form builder.

ALL OFFLINE / IN-MEMORY.  Tiny synthetic DataFrames (player IDs >= 900000) are
passed directly to ``build_asof_features``; the real CC BY-NC-SA corpus is never
read.  Each build writes to a tmp parquet so the IO path is exercised too.
No src.* / torch imports.
"""
from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import pytest

from domains.tennis.asof_features import (
    OUT_COLS,
    _ASOF_SUFFIXES,
    _RATE_MAP,
    build_asof_features,
)

_RATE_SUFS = [suf for suf, _ in _RATE_MAP]  # sidecar column suffixes


def _stats_row(eid: str, **rates) -> dict:
    """Build one match_stats row: p1_/p2_ rates default NaN unless given."""
    row = {"event_id": eid}
    for side in ("p1", "p2"):
        for suf in _RATE_SUFS:
            row[f"{side}_{suf}"] = rates.get(f"{side}_{suf}", float("nan"))
    return row


def _matches_row(eid: str, date: str, p1: int, p2: int, match_num: int = 1) -> dict:
    return {"event_id": eid, "date": date, "p1_id": p1, "p2_id": p2,
            "tour": "atp", "tourney_id": "t", "round": "R32", "match_num": match_num}


def _build(stats_rows, matches_rows, tmp_path) -> pd.DataFrame:
    ms = pd.DataFrame(stats_rows)
    mt = pd.DataFrame(matches_rows)
    out = build_asof_features(match_stats=ms, matches=mt,
                             out_path=str(Path(tmp_path) / "asof.parquet"))
    return pd.read_parquet(out)


def test_prior_only_mean_excludes_current(tmp_path):
    """Player 900001 plays 3 matches; match-3 asof == mean of matches 1-2 (not 3)."""
    pid, opp_base = 900001, 900100
    stats, mats = [], []
    aces = {1: 0.10, 2: 0.20, 3: 0.99}  # match-3 value must NOT enter its own asof
    for k in (1, 2, 3):
        eid = f"e{k}"
        opp = opp_base + k
        stats.append(_stats_row(eid, p1_ace_rate=aces[k], p1_1st_in_pct=0.6,
                               p1_1st_win_pct=0.7, p1_2nd_win_pct=0.5, p1_bp_saved_pct=0.6))
        mats.append(_matches_row(eid, f"2024-01-0{k}", pid, opp, match_num=k))
    df = _build(stats, mats, tmp_path).set_index("event_id")

    # Match 1: no prior -> NaN.  Match 3: mean(0.10, 0.20) = 0.15.
    assert math.isnan(df.loc["e1", "p1_ace_rate_asof"])
    assert df.loc["e2", "p1_ace_rate_asof"] == pytest.approx(0.10)  # only match-1
    assert df.loc["e3", "p1_ace_rate_asof"] == pytest.approx(0.15)  # mean of 1,2 not 3


def test_flip_future_no_change(tmp_path):
    """Changing a LATER match's stats leaves an EARLIER match's asof unchanged."""
    pid = 900002
    base_stats = [
        _stats_row("a", p1_ace_rate=0.10),
        _stats_row("b", p1_ace_rate=0.20),
        _stats_row("c", p1_ace_rate=0.30),
    ]
    mats = [
        _matches_row("a", "2024-02-01", pid, 900200, 1),
        _matches_row("b", "2024-02-02", pid, 900201, 2),
        _matches_row("c", "2024-02-03", pid, 900202, 3),
    ]
    df1 = _build(base_stats, mats, tmp_path).set_index("event_id")

    # Mutate the LAST match's stat only.
    mutated = [dict(r) for r in base_stats]
    mutated[2]["p1_ace_rate"] = 0.95
    df2 = _build(mutated, mats, tmp_path).set_index("event_id")

    # asof for matches a and b must be identical across the two builds.
    for eid in ("a", "b"):
        v1, v2 = df1.loc[eid, "p1_ace_rate_asof"], df2.loc[eid, "p1_ace_rate_asof"]
        assert (math.isnan(v1) and math.isnan(v2)) or v1 == pytest.approx(v2)


def test_slot_agnostic_history(tmp_path):
    """A player appears as p1 in one match and p2 in another; history aggregates both."""
    hero = 900003
    # Match 1: hero is p1 with ace_rate 0.10.
    # Match 2: hero is p2 with ace_rate 0.30.
    # Match 3: hero is p1 again -> asof == mean(0.10, 0.30) = 0.20.
    stats = [
        _stats_row("m1", p1_ace_rate=0.10),
        _stats_row("m2", p2_ace_rate=0.30),
        _stats_row("m3", p1_ace_rate=0.99),
    ]
    mats = [
        _matches_row("m1", "2024-03-01", hero, 900300, 1),
        _matches_row("m2", "2024-03-02", 900301, hero, 2),  # hero in p2 slot
        _matches_row("m3", "2024-03-03", hero, 900302, 3),
    ]
    df = _build(stats, mats, tmp_path).set_index("event_id")
    assert df.loc["m3", "p1_ace_rate_asof"] == pytest.approx(0.20)
    assert df.loc["m3", "p1_n_prior"] == 2


def test_n_prior_and_nan_on_zero(tmp_path):
    """n_prior counts strictly-prior matches; zero prior -> NaN asof cols."""
    pid = 900004
    stats = [_stats_row("g1", p1_ace_rate=0.10), _stats_row("g2", p1_ace_rate=0.20)]
    mats = [
        _matches_row("g1", "2024-04-01", pid, 900400, 1),
        _matches_row("g2", "2024-04-02", pid, 900401, 2),
    ]
    df = _build(stats, mats, tmp_path).set_index("event_id")

    # First match: no prior -> n_prior 0 and every asof col NaN.
    assert df.loc["g1", "p1_n_prior"] == 0
    for suf in _ASOF_SUFFIXES:
        assert math.isnan(df.loc["g1", f"p1_{suf}"])
    # Second match: one prior.
    assert df.loc["g2", "p1_n_prior"] == 1
    assert df.loc["g2", "p1_ace_rate_asof"] == pytest.approx(0.10)


def test_schema_and_diffs(tmp_path):
    """All expected columns present; diff == p1_asof - p2_asof."""
    p1, p2 = 900005, 900006
    # Give both players one prior so match-2 has non-NaN diffs.
    stats = [
        _stats_row("s1", p1_ace_rate=0.10, p1_1st_in_pct=0.6, p1_1st_win_pct=0.7,
                   p1_2nd_win_pct=0.5, p1_bp_saved_pct=0.6),
        _stats_row("s2", p2_ace_rate=0.30, p2_1st_in_pct=0.5, p2_1st_win_pct=0.6,
                   p2_2nd_win_pct=0.4, p2_bp_saved_pct=0.5),
        _stats_row("s3", p1_ace_rate=0.99, p2_ace_rate=0.99),
    ]
    mats = [
        _matches_row("s1", "2024-05-01", p1, 900500, 1),  # p1 plays
        _matches_row("s2", "2024-05-02", 900501, p2, 2),  # p2 plays (as p2)
        _matches_row("s3", "2024-05-03", p1, p2, 3),      # both have a prior
    ]
    df = _build(stats, mats, tmp_path)

    assert list(df.columns) == OUT_COLS  # exact schema + order
    assert len(df) == 3

    row = df.set_index("event_id").loc["s3"]
    for suf in _ASOF_SUFFIXES:
        v1, v2, d = row[f"p1_{suf}"], row[f"p2_{suf}"], row[f"diff_{suf}"]
        if math.isnan(v1) or math.isnan(v2):
            assert math.isnan(d)
        else:
            assert d == pytest.approx(v1 - v2)
    # p1's ace asof = 0.10, p2's = 0.30 -> diff = -0.20.
    assert row["p1_ace_rate_asof"] == pytest.approx(0.10)
    assert row["p2_ace_rate_asof"] == pytest.approx(0.30)
    assert row["diff_ace_rate_asof"] == pytest.approx(-0.20)


def test_row_count_one_to_one(tmp_path):
    """Output has exactly one row per input event_id."""
    stats = [_stats_row(f"r{k}", p1_ace_rate=0.1 * k) for k in range(1, 6)]
    mats = [_matches_row(f"r{k}", f"2024-06-0{k}", 900007, 900600 + k, k)
            for k in range(1, 6)]
    df = _build(stats, mats, tmp_path)
    assert len(df) == 5
    assert df["event_id"].nunique() == 5
    assert set(df["event_id"]) == {f"r{k}" for k in range(1, 6)}
