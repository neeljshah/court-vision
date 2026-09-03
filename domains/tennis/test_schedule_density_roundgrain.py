"""S136 -- the round-grain tennis schedule-density / travel tables: the strictly-before rule at
(tourney start date, ROUND) grain, and the permutation S122 pinned, now unwound."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from domains.tennis import schedule_density_roundgrain as rg

_ATP_RG = "data/domains/tennis/schedule_density_rg.parquet"
_TRAVEL_RG = "data/domains/tennis/travel_scouting_rg.parquet"
_ROUNDS = ["R128", "R64", "R32", "R16", "QF", "SF", "F"]


def _one_tourney_spine() -> pd.DataFrame:
    """One player's seven-round run at a single tournament -- every match on the SAME date, as
    Sackmann publishes it -- plus one earlier match 3 days before and one 30 days before."""
    rows = [("2020-06-01", "T0", "R32", 1, 90), ("2020-05-05", "T1", "R32", 1, 91)]
    rows += [("2020-06-04", "T2", r, 1, 100 + i) for i, r in enumerate(_ROUNDS)]
    return pd.DataFrame([{
        "event_id": "%s-atp-%s-%d-%d-1" % (d.replace("-", ""), t, a, b),
        "date": d, "tourney_id": t, "tourney_name": "Adelaide", "surface": "Hard",
        "round": rnd, "p1_id": a, "p2_id": b, "p1_name": "Ann", "p2_name": "Opp%d" % b,
    } for d, t, rnd, a, b in rows])


def _build(tmp_path, fn, stem):
    spine = tmp_path / "spine.parquet"
    _one_tourney_spine().to_parquet(spine, index=False)
    return pd.read_parquet(fn(spine, tmp_path / ("%s.parquet" % stem)))


def test_the_seven_rounds_of_one_tourney_serve_the_chronological_sequence(tmp_path) -> None:
    out = _build(tmp_path, rg.build_density, "d")
    ann = out[out["player_id"] == 1].sort_values("round_ord")
    run = ann[ann["date"] == pd.Timestamp("2020-06-04")]
    # R128 already sees the match 3 days earlier; each later round adds exactly one.
    assert run["matches_last_7d"].tolist() == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
    assert run["matches_last_14d"].tolist() == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
    # the 30-days-back match is outside both windows of the 2020-06-01 one
    older = ann[ann["date"] == pd.Timestamp("2020-06-01")].iloc[0]
    assert older["matches_last_7d"] == 0.0 and older["matches_last_14d"] == 0.0


def test_rest_days_is_dropped_as_closed_at_limit(tmp_path) -> None:
    out = _build(tmp_path, rg.build_density, "d")
    assert "rest_days" not in out.columns and "round" in out.columns


def test_an_unknown_round_code_fails_loudly_instead_of_sorting_to_one_end() -> None:
    with pytest.raises(ValueError, match="unknown Sackmann round code"):
        rg.round_ord(pd.Series(["R32", "Q1"]))


def _brute_force(dates: np.ndarray, ords: np.ndarray, days: int) -> np.ndarray:
    """The rule spelled out row by row: count rows with (date < D) or (date == D and round < r),
    inside the trailing window (D - days, D]. Independent of the searchsorted implementation."""
    floor = dates - np.timedelta64(days, "D")
    return np.array([int((((dates < d) | ((dates == d) & (ords < r))) & (dates > floor[i])).sum())
                     for i, (d, r) in enumerate(zip(dates, ords))], float)


def test_the_landed_atp_table_is_strictly_before_at_date_round_grain() -> None:
    """Recomputed row by row on 300 sampled players of the REAL corpus (not a head slice)."""
    frame = pd.read_parquet(_ATP_RG)
    players = pd.Series(frame["player_id"].unique()).sample(300, random_state=20260903)
    sample = frame[frame["player_id"].isin(players)]
    assert len(sample) > 3000
    for _, group in sample.groupby("player_id", sort=False):
        group = group.sort_values(["date", "round_ord"], kind="mergesort")
        dates = group["date"].to_numpy("datetime64[ns]")
        ords = group["round_ord"].to_numpy()
        for days in (7, 14):
            assert np.array_equal(group["matches_last_%dd" % days].to_numpy(float),
                                  _brute_force(dates, ords, days))


def test_the_wimbledon_champion_no_longer_serves_a_permutation() -> None:
    """S122 measured 0,3,4,5,1,6,2 for the 2025 Wimbledon champion's seven matches."""
    matches = pd.read_parquet("data/domains/tennis/matches.parquet")
    draw = matches[matches["tourney_id"] == "2025-540"]
    final = draw[draw["round"] == "F"].iloc[0]
    champion = int(final["p1_id"] if final["winner"] == 1 else final["p2_id"])
    keyed = pd.read_parquet(_ATP_RG).set_index(["event_id", "player_id"])["matches_last_7d"]
    order = {r: i for i, r in enumerate(_ROUNDS)}
    served = sorted((order[row["round"]], float(keyed.loc[(row["event_id"], champion)]))
                    for _, row in draw.iterrows()
                    if champion in (row["p1_id"], row["p2_id"]))
    assert [v for _, v in served] == [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0]


def test_travel_reads_the_previous_city_under_the_round_order(tmp_path) -> None:
    out = _build(tmp_path, rg.build_travel, "t")
    ann = out[out["player"] == "Ann"].sort_values(["date", "round_ord"])
    assert pd.isna(ann.iloc[0]["miles_flown_in"])          # debut: no prior city, never 0-filled
    # one venue in this spine, so every later appearance is a resolved 0-mile hop, in ROUND order
    assert ann["miles_flown_in"].tolist()[1:] == [0.0] * (len(ann) - 1)
    assert ann["venue_altitude_m"].notna().all()


def test_the_landed_travel_table_keeps_one_row_per_appearance() -> None:
    frame = pd.read_parquet(_TRAVEL_RG)
    assert len(frame) == 55446 and frame["round_ord"].notna().all()
    first = frame.sort_values(["date", "round_ord"], kind="mergesort").groupby("player").head(1)
    assert first["miles_flown_in"].isna().all()


def test_a_within_tourney_later_round_never_reports_a_flight() -> None:
    """Every round of a tourney shares one city, so under the round order a player's second and
    later appearances at that event read 0 miles -- recorded, not hidden (memo section 3)."""
    frame = pd.read_parquet(_TRAVEL_RG).sort_values(["player", "date", "round_ord"],
                                                    kind="mergesort")
    later = frame.duplicated(["player", "date"], keep="first")
    assert later.sum() > 10000
    assert frame.loc[later, "miles_flown_in"].fillna(0.0).eq(0.0).all()
