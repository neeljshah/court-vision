"""Per-file tests: possession extraction + point-model normalization/backoff."""
import numpy as np
import pandas as pd

from domains.basketball_nba.sim2.possession_model import (
    time_bucket, margin_bucket, cell_index, extract_possessions,
    add_state_buckets, PossessionModel, N_CELLS, PMAX)


def _act(n, at, tid, period, mmss, sh, sa, made=None):
    m, s = mmss
    a = {"actionNumber": n, "actionType": at, "teamId": tid, "period": period,
         "clock": "PT%02dM%05.2fS" % (m, s), "scoreHome": sh, "scoreAway": sa,
         "description": ""}
    if made is not None:
        a["shotResult"] = "Made" if made else "Missed"
    return a


def test_bucket_helpers():
    assert time_bucket(1, 700) == 0 and time_bucket(3, 100) == 2
    assert time_bucket(4, 200) == 3 and time_bucket(4, 100) == 4
    assert time_bucket(5, 100) == 5
    assert margin_bucket(-100) == 0 and margin_bucket(0) == 3 and margin_bucket(100) == 6
    # symmetric around 0
    assert margin_bucket(-4) + margin_bucket(4) == 6


def test_extract_points_and_alternation():
    # team 10 (home) scores a 2, then team 20 (away) scores a 3
    actions = [
        _act(1, "2pt", 10, 1, (11, 40.0), 2, 0, made=True),   # home makes -> poss ends
        _act(2, "3pt", 20, 1, (11, 20.0), 2, 3, made=True),   # away makes -> poss ends
        _act(3, "2pt", 10, 1, (11, 0.0), 4, 3, made=True),
    ]
    ps = extract_possessions(actions)
    assert len(ps) >= 2
    # home inferred correctly: first possession is home with 2 pts
    assert ps[0]["off_is_home"] is True and ps[0]["points"] == 2
    assert ps[1]["off_is_home"] is False and ps[1]["points"] == 3
    # points never negative, capped at PMAX
    assert all(0 <= p["points"] <= PMAX for p in ps)


def test_point_model_normalized_and_backoff():
    rng = np.random.default_rng(0)
    n = 8000
    df = pd.DataFrame({
        "time_b": rng.integers(0, 6, n), "margin_b": rng.integers(0, 7, n),
        "off_t": rng.integers(0, 3, n), "def_t": rng.integers(0, 3, n),
        "pace_t": rng.integers(0, 3, n),
        "points": rng.choice([0, 2, 3], size=n, p=[0.55, 0.32, 0.13]),
    })
    m = PossessionModel.fit(df)
    cdf = m.point_cdf_matrix()
    assert cdf.shape == (N_CELLS, PMAX + 1)
    assert np.allclose(cdf[:, -1], 1.0)              # every row is a proper CDF
    assert np.all(np.diff(cdf, axis=1) >= -1e-9)     # monotone non-decreasing
    s = m.summary()
    assert s["n_full"] + s["n_backoff_marginal"] + s["n_global"] == N_CELLS
    assert s["n_backoff_marginal"] > 0               # sparse cells did back off


def test_add_state_buckets():
    df = pd.DataFrame({"period": [1, 4], "clock_start": [700.0, 100.0],
                       "off_margin": [0.0, 10.0]})
    out = add_state_buckets(df)
    assert list(out["time_b"]) == [0, 4] and list(out["margin_b"]) == [3, 5]
