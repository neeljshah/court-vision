"""tests.soccer.test_asof_features — OFFLINE leak-free walk-forward checks.

Exercises domains.soccer.asof_features against a SMALL synthetic match_stats
DataFrame (no parquet read, no network).  Asserts the AS-OF rolling shot-quality
form is STRICTLY prior-only (snapshot-before-update), aggregates a team's home
AND away appearances, windows the last-N rolling mean correctly, NaNs on zero
prior history, and emits the full schema 1:1 with input rows.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest

from domains.soccer.asof_features import (
    ASOF_COLS,
    ROLL_N,
    build_asof_features,
    build_asof_frame,
)


def _row(date: str, home: str, away: str, hs: float, as_: float,
         hst: float, ast: float) -> dict:
    return {
        "event_id": f"{date}-E0-{home}-{away}",
        "date": pd.Timestamp(date), "div": "E0",
        "home_team": home, "away_team": away,
        "home_shots": hs, "away_shots": as_,
        "home_sot": hst, "away_sot": ast,
    }


@pytest.fixture()
def simple_df() -> pd.DataFrame:
    """Arsenal plays 3 matches (home, away, home); Chelsea / Spurs as foils."""
    rows = [
        # Arsenal home vs Chelsea: Arsenal 10 shots / 5 SoT
        _row("2024-08-10", "Arsenal", "Chelsea", 10, 6, 5, 2),
        # Arsenal away at Spurs: Arsenal (away) 8 shots / 3 SoT
        _row("2024-08-17", "Spurs", "Arsenal", 12, 8, 4, 3),
        # Arsenal home vs Spurs again: this is Arsenal's 3rd match
        _row("2024-08-24", "Arsenal", "Spurs", 14, 9, 7, 4),
    ]
    return pd.DataFrame(rows)


def test_prior_only_expanding_mean(simple_df: pd.DataFrame) -> None:
    """Arsenal's 3rd match AS-OF SoT-for = mean of its first 2 (5, 3) = 4.0.

    Match 1: Arsenal home SoT-for=5, shots-for=10.
    Match 2: Arsenal AWAY SoT-for=3, shots-for=8.
    Match 3 (home) snapshot must average ONLY those two priors.
    """
    out = build_asof_frame(simple_df).set_index("event_id")
    m3 = out.loc["2024-08-24-E0-Arsenal-Spurs"]
    assert m3["home_n_prior"] == 2
    assert m3["home_sot_for_asof"] == pytest.approx((5 + 3) / 2)
    assert m3["home_shots_for_asof"] == pytest.approx((10 + 8) / 2)
    # SoT-against: m1 Chelsea SoT=2, m2 Spurs SoT (vs Arsenal away) = home_sot=4
    assert m3["home_sot_against_asof"] == pytest.approx((2 + 4) / 2)
    assert m3["home_shots_against_asof"] == pytest.approx((6 + 12) / 2)


def test_home_or_away_aggregation(simple_df: pd.DataFrame) -> None:
    """A team's history combines BOTH its home and away appearances.

    On match 3 Arsenal has n_prior=2 (one home, one away).  If only home
    appearances were counted it would be 1.
    """
    out = build_asof_frame(simple_df).set_index("event_id")
    assert out.loc["2024-08-24-E0-Arsenal-Spurs", "home_n_prior"] == 2
    # Spurs (away in m3) also has 1 prior (it was home in m2)
    assert out.loc["2024-08-24-E0-Arsenal-Spurs", "away_n_prior"] == 1


def test_flip_future_no_change(simple_df: pd.DataFrame) -> None:
    """Mutating a LATER match must NOT change an EARLIER match's features.

    Recompute with match-3 stats wildly changed; matches 1 and 2 are identical.
    """
    base = build_asof_frame(simple_df).set_index("event_id")
    mutated = simple_df.copy()
    last = mutated.index[-1]
    mutated.loc[last, ["home_shots", "home_sot", "away_shots", "away_sot"]] = \
        [999, 999, 999, 999]
    after = build_asof_frame(mutated).set_index("event_id")
    feat = [c for c in ASOF_COLS if c != "event_id"]
    for eid in ["2024-08-10-E0-Arsenal-Chelsea", "2024-08-17-E0-Spurs-Arsenal"]:
        a = base.loc[eid, feat].astype(float).values
        b = after.loc[eid, feat].astype(float).values
        assert np.allclose(a, b, equal_nan=True), eid


def test_rolling_l10_windowing() -> None:
    """The last-N (N=10) rolling SoT-for uses only the most recent ROLL_N priors.

    Build ROLL_N+2 prior matches for one team with SoT-for = 0,1,2,...  The
    final match's l10 must average the last ROLL_N values, NOT all of them.
    """
    teamA = "Alpha"
    rows = []
    # opponents rotate so only Alpha accumulates a long history
    for k in range(ROLL_N + 2):
        opp = f"Opp{k}"
        d = f"2024-09-{k + 1:02d}"
        # Alpha home, SoT-for = k, shots-for = 20 (constant)
        rows.append(_row(d, teamA, opp, 20, 5, float(k), 2))
    # final probe match for Alpha (home) on a later date
    probe_date = "2024-10-01"
    rows.append(_row(probe_date, teamA, "Probe", 20, 5, 99, 2))
    df = pd.DataFrame(rows)
    out = build_asof_frame(df).set_index("event_id")
    probe = out.loc[f"{probe_date}-E0-{teamA}-Probe"]
    total_prior = ROLL_N + 2
    assert probe["home_n_prior"] == total_prior
    # expanding mean = mean(0..ROLL_N+1)
    expected_exp = sum(range(total_prior)) / total_prior
    assert probe["home_sot_for_asof"] == pytest.approx(expected_exp)
    # rolling = mean of last ROLL_N values = mean(2 .. ROLL_N+1)
    last_vals = list(range(2, total_prior))
    assert len(last_vals) == ROLL_N
    assert probe["home_sot_for_l10"] == pytest.approx(sum(last_vals) / ROLL_N)
    # rolling != expanding here (windowing genuinely active)
    assert probe["home_sot_for_l10"] != pytest.approx(expected_exp)


def test_nan_on_zero_prior(simple_df: pd.DataFrame) -> None:
    """First-ever appearances have n_prior==0 and ALL features NaN."""
    out = build_asof_frame(simple_df).set_index("event_id")
    m1 = out.loc["2024-08-10-E0-Arsenal-Chelsea"]
    assert m1["home_n_prior"] == 0 and m1["away_n_prior"] == 0
    nan_feats = [
        "home_sot_for_asof", "home_shots_for_asof", "home_sot_against_asof",
        "away_sot_for_asof", "away_shots_for_asof",
        "diff_sot_for_asof", "home_sot_for_l10", "away_sot_for_l10",
        "home_sot_ratio_for_asof",
    ]
    for c in nan_feats:
        assert math.isnan(float(m1[c])), c


def test_sot_ratio_prior_only(simple_df: pd.DataFrame) -> None:
    """AS-OF SoT ratio = mean of prior per-match (sot_for/shots_for) ratios."""
    out = build_asof_frame(simple_df).set_index("event_id")
    m3 = out.loc["2024-08-24-E0-Arsenal-Spurs"]
    # m1 ratio = 5/10 = 0.5 ; m2 (Arsenal away) ratio = 3/8 = 0.375
    assert m3["home_sot_ratio_for_asof"] == pytest.approx((0.5 + 0.375) / 2)


def test_schema_and_diffs(simple_df: pd.DataFrame) -> None:
    """Output has exactly ASOF_COLS and diffs = home - away (where defined)."""
    out = build_asof_frame(simple_df)
    assert list(out.columns) == list(ASOF_COLS)
    out_i = out.set_index("event_id")
    m3 = out_i.loc["2024-08-24-E0-Arsenal-Spurs"]
    assert m3["diff_sot_for_asof"] == pytest.approx(
        m3["home_sot_for_asof"] - m3["away_sot_for_asof"])
    assert m3["diff_shots_against_asof"] == pytest.approx(
        m3["home_shots_against_asof"] - m3["away_shots_against_asof"])


def test_one_to_one_row_count(simple_df: pd.DataFrame) -> None:
    """Output row count == input match count; event_ids preserved 1:1."""
    out = build_asof_frame(simple_df)
    assert len(out) == len(simple_df)
    assert set(out["event_id"]) == set(simple_df["event_id"])


def test_nan_stat_row_skipped() -> None:
    """A prior match with NaN stats does not count toward n_prior or means."""
    rows = [
        _row("2024-08-01", "Alpha", "Beta", 10, 5, 5, 2),
        # NaN stats row for Alpha (should be skipped in its history)
        _row("2024-08-08", "Alpha", "Gamma", np.nan, 5, np.nan, 2),
        _row("2024-08-15", "Alpha", "Delta", 8, 4, 3, 1),
    ]
    out = build_asof_frame(pd.DataFrame(rows)).set_index("event_id")
    m3 = out.loc["2024-08-15-E0-Alpha-Delta"]
    # only the first finite match counts -> n_prior == 1, mean == 5
    assert m3["home_n_prior"] == 1
    assert m3["home_sot_for_asof"] == pytest.approx(5.0)


def test_build_writes_parquet(simple_df: pd.DataFrame, tmp_path: Path) -> None:
    """build_asof_features(df, out_path) writes a 1:1 parquet with the schema."""
    out_file = build_asof_features(match_stats=simple_df,
                                   out_path=str(tmp_path / "asof.parquet"))
    assert out_file.exists()
    got = pq.read_table(out_file).to_pandas()
    assert list(got.columns) == list(ASOF_COLS)
    assert len(got) == len(simple_df)
