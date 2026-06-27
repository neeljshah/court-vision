"""tests.soccer.test_asof_discipline_features -- OFFLINE leak-free EW as-of checks.

Exercises domains.soccer.asof_discipline_features against a SMALL synthetic
match_stats DataFrame (no parquet read, no network). Asserts the trailing EW
discipline/possession-proxy form is STRICTLY prior-only (snapshot-before-update),
aggregates a team's home AND away appearances, EW-recencies correctly, NaNs on zero
prior history, and emits the full schema 1:1 with input rows.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest

from domains.soccer.asof_discipline_features import (
    ALPHA, ASOF_DISC_COLS, build_asof_disc_frame, build_asof_discipline_features,
)


def _row(date: str, home: str, away: str, *, hc=5, ac=4, hf=10, af=11,
         hy=1, ay=2, hr=0, ar=0, hsr=0.5, asr=0.4) -> dict:
    return {
        "event_id": f"{date}-E0-{home}-{away}",
        "date": pd.Timestamp(date), "div": "E0",
        "home_team": home, "away_team": away,
        "home_corners": hc, "away_corners": ac,
        "home_fouls": hf, "away_fouls": af,
        "home_yellow": hy, "away_yellow": ay,
        "home_red": hr, "away_red": ar,
        "home_sot_ratio": hsr, "away_sot_ratio": asr,
    }


@pytest.fixture()
def simple_df() -> pd.DataFrame:
    rows = [
        _row("2024-08-10", "Arsenal", "Chelsea", hc=8, hf=12, hy=1),
        _row("2024-08-17", "Spurs", "Arsenal", hc=6, ac=4, hf=9, af=10, ay=3),
        _row("2024-08-24", "Arsenal", "Spurs", hc=14, hf=7, hy=2),
    ]
    return pd.DataFrame(rows)


def test_first_appearance_seeds_then_ew(simple_df: pd.DataFrame) -> None:
    """Arsenal m3 home corners EW = EW over its 2 priors (m1 home=8, m2 away=4)."""
    out = build_asof_disc_frame(simple_df).set_index("event_id")
    m3 = out.loc["2024-08-24-E0-Arsenal-Spurs"]
    assert m3["home_n_prior"] == 2
    # m1 seeds EW=8; m2 (Arsenal away corners = ac=4) folds: 8 + ALPHA*(4-8)
    expected = 8.0 + ALPHA * (4.0 - 8.0)
    assert m3["home_corners_asof"] == pytest.approx(expected)


def test_home_or_away_aggregation(simple_df: pd.DataFrame) -> None:
    """A team's history combines BOTH home and away appearances."""
    out = build_asof_disc_frame(simple_df).set_index("event_id")
    assert out.loc["2024-08-24-E0-Arsenal-Spurs", "home_n_prior"] == 2
    assert out.loc["2024-08-24-E0-Arsenal-Spurs", "away_n_prior"] == 1


def test_flip_future_no_change(simple_df: pd.DataFrame) -> None:
    """Mutating a LATER match must NOT change an EARLIER match's features (leak-free)."""
    base = build_asof_disc_frame(simple_df).set_index("event_id")
    mutated = simple_df.copy()
    last = mutated.index[-1]
    for c in ("home_corners", "home_fouls", "home_yellow", "home_red",
              "home_sot_ratio"):
        mutated.loc[last, c] = 999
    after = build_asof_disc_frame(mutated).set_index("event_id")
    feat = [c for c in ASOF_DISC_COLS if c != "event_id"]
    for eid in ["2024-08-10-E0-Arsenal-Chelsea", "2024-08-17-E0-Spurs-Arsenal"]:
        a = base.loc[eid, feat].astype(float).values
        b = after.loc[eid, feat].astype(float).values
        assert np.allclose(a, b, equal_nan=True), eid


def test_nan_on_zero_prior(simple_df: pd.DataFrame) -> None:
    """First-ever appearances have n_prior==0 and ALL feature cells NaN."""
    out = build_asof_disc_frame(simple_df).set_index("event_id")
    m1 = out.loc["2024-08-10-E0-Arsenal-Chelsea"]
    assert m1["home_n_prior"] == 0 and m1["away_n_prior"] == 0
    for c in ASOF_DISC_COLS:
        if c.endswith("_asof"):
            assert math.isnan(float(m1[c])), c


def test_missing_stat_carries_forward() -> None:
    """A NaN stat in a prior match does not zero-inject; its EW carries forward."""
    rows = [
        _row("2024-08-01", "Alpha", "Beta", hc=10),
        _row("2024-08-08", "Alpha", "Gamma", hc=np.nan, hf=8),
        _row("2024-08-15", "Alpha", "Delta", hc=4),
    ]
    out = build_asof_disc_frame(pd.DataFrame(rows)).set_index("event_id")
    m3 = out.loc["2024-08-15-E0-Alpha-Delta"]
    # corners: m1 seeds 10; m2 corners NaN -> not updated -> EW still 10
    assert m3["home_corners_asof"] == pytest.approx(10.0)
    # but a finite stat that match (fouls) DID count the row toward n_prior
    assert m3["home_n_prior"] == 2


def test_schema_and_diffs(simple_df: pd.DataFrame) -> None:
    """Output has exactly ASOF_DISC_COLS and diffs = home - away (where defined)."""
    out = build_asof_disc_frame(simple_df)
    assert list(out.columns) == list(ASOF_DISC_COLS)
    out_i = out.set_index("event_id")
    m3 = out_i.loc["2024-08-24-E0-Arsenal-Spurs"]
    assert m3["diff_corners_asof"] == pytest.approx(
        m3["home_corners_asof"] - m3["away_corners_asof"])
    assert m3["diff_fouls_asof"] == pytest.approx(
        m3["home_fouls_asof"] - m3["away_fouls_asof"])


def test_one_to_one_row_count(simple_df: pd.DataFrame) -> None:
    out = build_asof_disc_frame(simple_df)
    assert len(out) == len(simple_df)
    assert set(out["event_id"]) == set(simple_df["event_id"])


def test_empty_input_empty_schema() -> None:
    out = build_asof_disc_frame(pd.DataFrame(columns=["event_id"]))
    assert list(out.columns) == list(ASOF_DISC_COLS)
    assert len(out) == 0


def test_build_writes_parquet(simple_df: pd.DataFrame, tmp_path: Path) -> None:
    out_file = build_asof_discipline_features(
        match_stats=simple_df, out_path=str(tmp_path / "disc.parquet"))
    assert out_file.exists()
    got = pq.read_table(out_file).to_pandas()
    assert list(got.columns) == list(ASOF_DISC_COLS)
    assert len(got) == len(simple_df)
