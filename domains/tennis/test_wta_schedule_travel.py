"""S122 -- the WTA schedule-density / travel siblings: strictly-before, wiring, and the
tourney-date LEAK that keeps both families out of the as-of bridge."""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.tennis import wta_schedule_travel as mod
from scripts.platformkit.foundry import asof_supply


def _spine() -> pd.DataFrame:
    """Three matches for player 1, each against a fresh opponent, on WTA-shaped event_ids
    whose tourney_id CONTAINS DASHES -- so the p1 id is not at split position 4. Each match
    carries a DISTINCT date, which the real Sackmann corpus does not (see the leak test)."""
    rows = [("2020-01-01", 1, 2, "Ann", "Bea"), ("2020-01-05", 1, 3, "Ann", "Cat"),
            ("2020-03-01", 1, 4, "Ann", "Dee")]
    return pd.DataFrame([{
        "event_id": "%s-wta-2020-W-SL-AUS-01A-2020-%d-%d-1" % (d.replace("-", ""), a, b),
        "date": d, "tour": "wta", "tourney_id": "W-SL-AUS-01A-2020", "tourney_name": "Adelaide",
        "surface": "Hard", "p1_id": a, "p2_id": b, "p1_name": pa, "p2_name": pb,
    } for d, a, b, pa, pb in rows])


def _build(tmp_path, fn):
    spine = tmp_path / "wta_matches.parquet"
    _spine().to_parquet(spine, index=False)
    return pd.read_parquet(fn(spine=spine, out_dir=tmp_path))


def test_a_match_on_date_d_sees_only_matches_strictly_before_d(tmp_path) -> None:
    ann = _build(tmp_path, mod.build_schedule_density_wta)
    ann = ann[ann["player_id"] == 1].sort_values("date")
    rest = ann["rest_days"].tolist()
    assert pd.isna(rest[0])                      # debut sees nothing
    assert rest[1:] == [4.0, 56.0]               # the gaps BACKWARD, never a future match
    assert ann["matches_last_7d"].tolist() == [0.0, 1.0, 0.0]
    assert ann["matches_last_14d"].tolist() == [0.0, 1.0, 0.0]


def test_every_single_appearance_player_is_an_honest_nan(tmp_path) -> None:
    out = _build(tmp_path, mod.build_schedule_density_wta)
    others = out[out["player_id"] != 1]
    assert len(others) == 3 and others["rest_days"].isna().all()
    assert (others["matches_last_7d"] == 0.0).all()


def test_travel_first_appearance_has_no_prior_city(tmp_path) -> None:
    out = _build(tmp_path, mod.build_travel_scouting_wta)
    assert not out.empty and out["venue_city"].eq("Adelaide").all()
    first = out.sort_values("date").groupby("player").head(1)
    assert first["miles_flown_in"].isna().all()   # no prior city -> honest NaN, never 0
    assert out["venue_altitude_m"].notna().all()


def test_the_side_is_read_from_the_end_of_a_dashed_event_id() -> None:
    """The S122 repair in `asof_supply._sides`: a dashed tourney_id shifts the head, so
    `str[4]` is "SL" on this id while `str[-3]`/`str[-2]` are the real p1 / p2 ids."""
    eid = "20200101-wta-2020-W-SL-AUS-01A-2020-11-22-1"
    assert eid.split("-")[4] == "SL"
    index = pd.Index([eid, "20150104-atp-2015-339-105357-105733-1"])
    a, b = asof_supply._sides(asof_supply.REGISTRY["tennis_serve_return_profiles"],
                             pd.DataFrame(index=index))
    assert list(a) == ["11", "105357"] and list(b) == ["22", "105733"]


def test_neither_family_is_declared_because_the_date_is_the_tourney_date() -> None:
    """The leak that keeps both out of the bridge, pinned on the REAL corpus: every match of
    a tournament carries ONE date, so a trailing-window count cannot order them and 46 pct of
    rows read zero days of rest. Re-registering these columns must fail this test first."""
    assert "tennis_schedule_density" not in asof_supply.REGISTRY
    assert "tennis_travel_scouting" not in asof_supply.REGISTRY
    for path in ("data/domains/tennis/matches.parquet",
                 "data/domains/tennis/wta_matches.parquet"):
        spine = pd.read_parquet(path)
        assert spine.groupby("tourney_id")["date"].nunique().eq(1).all()
    density = pd.concat([pd.read_parquet("data/domains/tennis/schedule_density.parquet"),
                         pd.read_parquet("data/domains/tennis/schedule_density_wta.parquet")],
                        ignore_index=True)
    assert np.isclose(density["rest_days"].eq(0).mean(), 0.4618, atol=5e-4)
