"""Per-file test for domains.soccer.prop_recal (network-free, canned df).

  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/test_prop_recal.py -q
"""
from __future__ import annotations

import json

import pandas as pd

from domains.soccer.prop_recal import (
    MIN_N,
    fit_recalibrators,
    load_recal,
    pava,
    recalibrate,
)


# ---------------------------------------------------------------------------
# PAVA -- hand-checked examples
# ---------------------------------------------------------------------------
def test_pava_already_monotone_unchanged():
    # x=[.1,.2,.3,.4], y=[0,0,1,1] is already non-decreasing -> unchanged.
    xk, yk = pava([0.1, 0.2, 0.3, 0.4], [0, 0, 1, 1])
    assert xk == [0.1, 0.2, 0.3, 0.4]
    assert yk == [0.0, 0.0, 1.0, 1.0]


def test_pava_pools_violation_to_mean():
    # y=[1,0,0] violates monotonicity; PAVA pools ALL three to the common mean
    # (1+0+0)/3 = 1/3 so the result is non-decreasing (flat).
    xk, yk = pava([0.1, 0.2, 0.3], [1, 0, 0])
    assert xk == [0.1, 0.2, 0.3]
    assert all(abs(v - 1.0 / 3.0) < 1e-9 for v in yk)
    # non-decreasing
    assert all(yk[i] <= yk[i + 1] + 1e-12 for i in range(len(yk) - 1))


def test_pava_partial_pool():
    # y=[0,1,0,1]: the middle 1,0 pool to 0.5; result [0,0.5,0.5,1] is monotone.
    xk, yk = pava([0.1, 0.2, 0.3, 0.4], [0, 1, 0, 1])
    assert yk == [0.0, 0.5, 0.5, 1.0]
    assert all(yk[i] <= yk[i + 1] + 1e-12 for i in range(len(yk) - 1))


def test_pava_pools_duplicate_x():
    # Duplicate x are averaged first: x=[.2,.2] y=[0,1] -> single knot at 0.5.
    xk, yk = pava([0.2, 0.2, 0.5], [0, 1, 1])
    assert xk == [0.2, 0.5]
    assert yk == [0.5, 1.0]


# ---------------------------------------------------------------------------
# recalibrate -- interpolation, clamping, identity
# ---------------------------------------------------------------------------
def _recal_table():
    # Under-confident low / over-confident mid map (rough WC shape).
    return {"Shots": {"x": [0.0, 0.026, 0.5, 1.0],
                      "y": [0.0, 0.058, 0.45, 1.0], "n": 300}}


def test_recalibrate_interpolates_between_knots():
    recal = _recal_table()
    # exactly on a knot -> that knot's y
    assert abs(recalibrate("Shots", 0.026, recal) - 0.058) < 1e-9
    # halfway between x=0.5 (y=0.45) and x=1.0 (y=1.0) -> 0.725
    mid = recalibrate("Shots", 0.75, recal)
    assert abs(mid - 0.725) < 1e-6
    # under-confident low region is lifted: raw 0.013 (half of 0.026) -> ~0.029
    lifted = recalibrate("Shots", 0.013, recal)
    assert lifted > 0.013


def test_recalibrate_clamps_ends_and_range():
    recal = _recal_table()
    assert recalibrate("Shots", -5.0, recal) == 0.0   # below range -> first knot
    assert recalibrate("Shots", 9.0, recal) == 1.0     # above range -> last knot
    out = recalibrate("Shots", 0.3, recal)
    assert 0.0 <= out <= 1.0


def test_recalibrate_identity_when_stat_missing():
    recal = _recal_table()
    assert recalibrate("Goals", 0.42, recal) == 0.42   # stat not fitted -> identity


def test_recalibrate_identity_when_recal_empty():
    assert recalibrate("Shots", 0.42, {}) == 0.42


def test_recalibrate_never_raises_on_bad_input():
    assert recalibrate("Shots", float("nan"), _recal_table()) == 0.0
    assert recalibrate("Shots", None, _recal_table()) == 0.0  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# load_recal
# ---------------------------------------------------------------------------
def test_load_recal_absent_returns_empty():
    assert load_recal("does/not/exist/prop_recal.json") == {}


def test_load_recal_roundtrip(tmp_path):
    p = tmp_path / "prop_recal.json"
    payload = {"as_of": "2026-06-17T00:00:00Z", "mode": "strict leak-free",
               "min_n": MIN_N,
               "per_stat": {"Shots": {"x": [0.0, 0.5, 1.0],
                                      "y": [0.0, 0.4, 1.0], "n": 200}}}
    p.write_text(json.dumps(payload), encoding="ascii")
    loaded = load_recal(str(p))
    assert "Shots" in loaded
    assert loaded["Shots"]["x"] == [0.0, 0.5, 1.0]
    assert loaded["Shots"]["n"] == 200


# ---------------------------------------------------------------------------
# fit_recalibrators -- tiny canned df, returns a dict; thin stats skipped
# ---------------------------------------------------------------------------
def _canned_df():
    """A few dated matches, 2 players. Far fewer than MIN_N pairs per stat, so
    every stat should be SKIPPED (identity) -- we assert it returns a dict and
    does not fit noise, and writes a well-formed JSON."""
    rows = []
    cols_zero = {
        "shotsOnTarget": 0.0, "foulsCommitted": 0.0, "foulsSuffered": 0.0,
        "yellowCards": 0.0, "redCards": 0.0, "goalAssists": 0.0, "offsides": 0.0,
        "totalGoals": 0.0, "saves": 0.0,
    }
    plan = [
        ("E1", "2026-01-01", "A", 90, 3.0), ("E1", "2026-01-01", "B", 90, 0.0),
        ("E2", "2026-01-05", "A", 90, 4.0), ("E2", "2026-01-05", "B", 90, 1.0),
        ("E3", "2026-01-09", "A", 90, 2.0), ("E3", "2026-01-09", "B", 90, 0.0),
    ]
    for eid, date, pid, mins, shots in plan:
        r = {"event_id": eid, "date": date, "player_id": pid, "position": "F",
             "minutes": float(mins), "totalShots": float(shots)}
        r.update(cols_zero)
        rows.append(r)
    return pd.DataFrame(rows)


def test_fit_recalibrators_returns_dict_thin_skipped(tmp_path):
    out = tmp_path / "prop_recal.json"
    res = fit_recalibrators(_canned_df(), stats=["Shots"], out_path=str(out))
    assert isinstance(res, dict)
    # Far below MIN_N pairs -> Shots is skipped (identity), so it is NOT fitted.
    assert "Shots" not in res
    # A well-formed JSON is still written with the schema keys.
    payload = json.loads(out.read_text(encoding="ascii"))
    assert payload["min_n"] == MIN_N
    assert "as_of" in payload and "per_stat" in payload
    assert payload["per_stat"] == {}


def test_fit_recalibrators_bad_input_never_raises(tmp_path):
    out = tmp_path / "prop_recal.json"
    assert fit_recalibrators(None, out_path=str(out)) == {}
    assert fit_recalibrators(pd.DataFrame(), out_path=str(out)) == {}
