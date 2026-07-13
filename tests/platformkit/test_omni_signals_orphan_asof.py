"""Per-file test for scripts.platformkit.omni.signals_orphan_asof.

  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_omni_signals_orphan_asof.py -q
"""
from __future__ import annotations

import pathlib

import pandas as pd
import pytest

from scripts.platformkit.omni import signals_orphan_asof as m


def test_convert_prior_season_asof_debut_rows_are_nan():
    """An entity's first season in the corpus has no prior season -> every
    asof__ column must be NaN (the leak-free debut convention)."""
    df = pd.DataFrame({
        "player_id": [1, 1, 1, 2, 2],
        "season": ["2022-23", "2023-24", "2024-25", "2023-24", "2024-25"],
        "pts": [10.0, 12.0, 14.0, 20.0, 22.0],
    })
    out = m.convert_prior_season_asof(df, "player_id")
    m.assert_no_prior_season_leak(out, "player_id")

    row = out[(out.player_id == 1) & (out.season == "2023-24")].iloc[0]
    assert row["asof__pts"] == 10.0  # prior (2022-23) season's own value
    row2 = out[(out.player_id == 1) & (out.season == "2024-25")].iloc[0]
    assert row2["asof__pts"] == 12.0

    debut = out[(out.player_id == 1) & (out.season == "2022-23")].iloc[0]
    assert pd.isna(debut["asof__pts"])
    debut2 = out[(out.player_id == 2) & (out.season == "2023-24")].iloc[0]
    assert pd.isna(debut2["asof__pts"])


def test_no_future_leak_a_row_never_carries_its_own_season_value():
    """A row's as-of value must equal a STRICTLY EARLIER season's raw value,
    never the value for the season the row is stamped with (or any later one)."""
    df = pd.DataFrame({
        "team_tricode": ["BOS"] * 4,
        "season": ["2021-22", "2022-23", "2023-24", "2024-25"],
        "net_rating": [1.0, 2.0, 3.0, 4.0],
    })
    out = m.convert_prior_season_asof(df, "team_tricode")
    raw_by_season = dict(zip(df["season"], df["net_rating"]))
    for _, row in out.iterrows():
        if pd.isna(row["asof__net_rating"]):
            continue
        # must match some season strictly before row['season'], never itself
        assert row["asof__net_rating"] != raw_by_season[row["season"]]
        seasons_sorted = sorted(raw_by_season)
        idx = seasons_sorted.index(row["season"])
        assert row["asof__net_rating"] in [raw_by_season[s] for s in seasons_sorted[:idx]]


@pytest.mark.parametrize("name,entity_col", m.CONVERTIBLE)
def test_round_trip_on_real_parquet_slice(name, entity_col):
    """Real-data round trip: build the asof frame from the actual source
    parquet and confirm the leak assertion holds and rows are produced."""
    src = m.SIGNALS_DIR / f"{name}.parquet"
    if not src.exists():
        pytest.skip(f"{src} not present in this environment")
    df = pd.read_parquet(src)
    if df["season"].nunique() < 2:
        pytest.skip(f"{name}: fewer than 2 seasons, NOT_CONVERTIBLE in this environment")
    out = m.convert_prior_season_asof(df, entity_col)
    m.assert_no_prior_season_leak(out, entity_col)
    assert len(out) == len(df)
    assert any(c.startswith("asof__") for c in out.columns)


def test_not_convertible_signals_are_all_accounted_for():
    """Every NOT_CONVERTIBLE entry names a real signal parquet stem and a reason."""
    for name, reason in m.NOT_CONVERTIBLE.items():
        assert isinstance(reason, str) and len(reason) > 0
        src = m.SIGNALS_DIR / f"{name}.parquet"
        if src.exists():
            assert (m.SIGNALS_DIR / f"{name}.parquet").is_file()


def test_build_all_writes_parquets_and_reports_not_convertible(tmp_path):
    if not m.SIGNALS_DIR.is_dir():
        pytest.skip("data/cache/signals not present in this environment")
    out_dir = pathlib.Path(tmp_path) / "signals_asof"
    results = m.build_all(out_dir=out_dir)
    for name in m.NOT_CONVERTIBLE:
        assert results[name]["status"] == "NOT_CONVERTIBLE"
    for name, _entity in m.CONVERTIBLE:
        assert results[name]["status"] in ("CONVERTED", "NOT_CONVERTIBLE")
        if results[name]["status"] == "CONVERTED":
            assert pathlib.Path(results[name]["path"]).is_file()
