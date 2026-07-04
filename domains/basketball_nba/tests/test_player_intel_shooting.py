"""Per-file tests for player_intel_shooting.py -- run in isolation, never full suite."""
import pandas as pd
import pytest

from domains.basketball_nba.player_intel_shooting import (
    _aggregate,
    load_boxscores,
    rank_composite,
    rank_single_metric,
    window_rows,
)


def _toy_rows():
    # Player A: elite efficiency, high volume -- should clear all floors.
    # Player B: below FGA floor -- excluded from composite/eff tables.
    # Player C: below 3PA floor -- excluded from composite + 3P% table, but
    #           clears eFG%/TS% floor (fga_pg high enough).
    rows = []
    for g in range(25):
        rows.append(dict(
            game_id=f"g{g}", date=pd.Timestamp("2025-01-01") + pd.Timedelta(days=g),
            season="2024-25", player_id=1, player_name="Player A",
            fgm=8, fga=14, fg3m=4, fg3a=8, ftm=4, fta=4, pts=24,
        ))
        rows.append(dict(
            game_id=f"g{g}", date=pd.Timestamp("2025-01-01") + pd.Timedelta(days=g),
            season="2024-25", player_id=2, player_name="Player B",
            fgm=1, fga=2, fg3m=0, fg3a=0, ftm=0, fta=0, pts=2,
        ))
        # Player C: one 3PA every 5 games -> fg3a_pg = 5/25 = 0.2, well under
        # the 1.0 composite floor, while fga_pg=12 clears the 5.0 eff floor.
        rows.append(dict(
            game_id=f"g{g}", date=pd.Timestamp("2025-01-01") + pd.Timedelta(days=g),
            season="2024-25", player_id=3, player_name="Player C",
            fgm=6, fga=12, fg3m=0, fg3a=(1 if g % 5 == 0 else 0), ftm=2, fta=2, pts=14,
        ))
    return pd.DataFrame(rows)


def test_load_boxscores_has_required_columns():
    df = load_boxscores()
    for col in ["player_id", "player_name", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "pts", "season", "date"]:
        assert col in df.columns


def test_load_boxscores_missing_column_raises(tmp_path):
    bad = pd.DataFrame({"player_id": [1]})
    p = tmp_path / "bad.parquet"
    bad.to_parquet(p)
    with pytest.raises(ValueError):
        load_boxscores(str(p))


def test_aggregate_formulas_are_correct():
    rows = _toy_rows()
    g = _aggregate(rows)
    a = g[g["player_id"] == 1].iloc[0]
    # eFG% = (fgm + 0.5*fg3m) / fga = (8+2)/14 per game summed -> (200+50)/350
    assert a["efg_pct"] == pytest.approx((8 * 25 + 0.5 * 4 * 25) / (14 * 25))
    # TS% = pts / (2*(fga+0.44*fta))
    assert a["ts_pct"] == pytest.approx((24 * 25) / (2 * (14 * 25 + 0.44 * 4 * 25)))
    assert a["ft_pct"] == pytest.approx(1.0)
    assert a["fg3_pct"] == pytest.approx(0.5)


def test_window_rows_season_filter():
    rows = _toy_rows()
    out = window_rows(rows, "season_2024-25")
    assert len(out) == len(rows)
    out2 = window_rows(rows, "season_2099-00")
    assert len(out2) == 0


def test_window_rows_last_20_caps_per_player():
    rows = _toy_rows()
    out = window_rows(rows, "last_20")
    counts = out.groupby("player_id").size()
    assert (counts == 20).all()


def test_window_rows_unknown_raises():
    rows = _toy_rows()
    with pytest.raises(ValueError):
        window_rows(rows, "bogus_window")


def test_rank_composite_applies_floors():
    rows = _toy_rows()
    table = _aggregate(rows)
    survivors, excluded = rank_composite(table)
    names = set(survivors["player_name"])
    assert "Player A" in names
    assert "Player B" not in names  # fga_pg=2 < 5.0 floor
    assert "Player C" not in names  # fg3a_pg=0.04 < 1.0 floor
    assert excluded == 2


def test_rank_single_metric_fg3_pct_floor():
    rows = _toy_rows()
    table = _aggregate(rows)
    survivors, excluded = rank_single_metric(table, "fg3_pct")
    names = set(survivors["player_name"])
    assert "Player A" in names  # fg3a_pg = 8 >= 4.0
    assert "Player C" not in names  # fg3a_pg = 0.04 < 4.0
    assert excluded == 2  # B and C both fail


def test_rank_single_metric_ts_pct_floor():
    rows = _toy_rows()
    table = _aggregate(rows)
    survivors, excluded = rank_single_metric(table, "ts_pct")
    names = set(survivors["player_name"])
    assert "Player A" in names
    assert "Player C" in names  # fga_pg=12 >= 5.0
    assert "Player B" not in names  # fga_pg=2 < 5.0
    assert excluded == 1


def test_rank_single_metric_unsupported_raises():
    rows = _toy_rows()
    table = _aggregate(rows)
    with pytest.raises(ValueError):
        rank_single_metric(table, "reb_pct")


def test_no_fabricated_players_all_names_from_source():
    """Ranking output player_names must be a subset of source parquet names."""
    df = load_boxscores()
    from domains.basketball_nba.player_intel_shooting import compute_window_table
    table = compute_window_table(df, "season_2024-25")
    survivors, _ = rank_composite(table)
    source_names = set(df["player_name"].unique())
    assert set(survivors["player_name"]).issubset(source_names)
