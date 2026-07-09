"""Per-file test for domains.tennis.composition.pressure_composite.

Covers: as-of guard (a player's year-Y points never inform their own year-Y
profile), composition z-math, and high-leverage-floor exclusion.

Run: python -m pytest domains/tennis/composition/test_pressure_composite.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.tennis.composition.pressure_composite import (
    BASKET, HL_FLOOR, _asof_prior, _delta_yearly, add_composite,
)


def test_asof_prior_excludes_current_year():
    df = pd.DataFrame({
        "player_name": ["A", "A", "A"],
        "year": [2018, 2019, 2020],
        "n": [10, 20, 30],
    })
    out = _asof_prior(df, ["n"]).set_index("year")
    assert out.loc[2018, "n_prior"] == 0                # no earlier years
    assert out.loc[2019, "n_prior"] == 10               # only 2018
    assert out.loc[2020, "n_prior"] == 30               # 2018+2019, NOT 2020's own 30
    assert out.loc[2020, "n_prior"] != out["n"].sum()   # would be 60 if current year leaked in


def test_delta_yearly_asof_math():
    # Player A serves in 2018: break_point points 5/5 won, baseline (all points
    # that year) 5/10 won. In 2019 break_point points are all LOST (0/5). The
    # 2019 row's as-of delta must use ONLY 2018 history (prior year), so it
    # must equal 2018's own rate, never reflecting 2019's own 0% own-year rate.
    rows = []
    for _ in range(5):
        rows.append({"player_name": "A", "role": "serve", "won": 1, "date": "2018-06-01", "break_point": True})
    for _ in range(5):
        rows.append({"player_name": "A", "role": "serve", "won": 0, "date": "2018-06-01", "break_point": False})
    for _ in range(5):
        rows.append({"player_name": "A", "role": "serve", "won": 0, "date": "2019-06-01", "break_point": True})
    long_df = pd.DataFrame(rows)
    long_df["year"] = pd.to_datetime(long_df["date"]).dt.year

    out = _delta_yearly(long_df, "break_point", "serve").set_index("year")
    assert pd.isna(out.loc[2018, "value"])          # no prior years yet -> NaN, never 0
    expected_2019 = (5 / 5) - (5 / 10)               # 2018's bp_rate - 2018's baseline_rate
    assert abs(out.loc[2019, "value"] - expected_2019) < 1e-9


def test_add_composite_floor_exclusion_and_zmath():
    # 3 eligible player-years (hl_n_prior >= HL_FLOOR) with one basket column
    # varying and the rest constant (constant columns z-score to NaN -> skipped
    # in the row mean, isolating the math to the one varying column); a 4th
    # player-year one point below floor must be excluded entirely.
    rows = []
    for name, val in (("A", 1.0), ("B", 2.0), ("C", 3.0)):
        row = {"player_name": name, "year": 2020, "hl_n_prior": HL_FLOOR}
        for col in BASKET:
            row[col] = val if col == "bp_serve_delta" else 0.5
        rows.append(row)
    rows.append({"player_name": "D", "year": 2020, "hl_n_prior": HL_FLOOR - 1,
                 **{col: 9.0 for col in BASKET}})
    ing = pd.DataFrame(rows)

    elig, n_considered, n_excluded = add_composite(ing)
    assert n_considered == 4
    assert n_excluded == 1
    assert set(elig["player_name"]) == {"A", "B", "C"}

    # bp_serve_delta = [1,2,3] -> mean=2, population std=sqrt(2/3); the other 7
    # basket columns are constant (std=0) -> z=NaN -> excluded from the row
    # mean, so pressure_composite must equal that ONE surviving z exactly.
    mu, sd = 2.0, np.std([1.0, 2.0, 3.0])
    expected = {"A": (1.0 - mu) / sd, "B": (2.0 - mu) / sd, "C": (3.0 - mu) / sd}
    got = elig.set_index("player_name")["pressure_composite"]
    for name, exp in expected.items():
        assert abs(got[name] - exp) < 1e-9
