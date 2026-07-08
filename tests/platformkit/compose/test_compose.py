"""compose lane tests: as-of leak guard + planted-signal/pure-noise end-to-end.

The gate must DETECT a planted signal and REFUSE pure noise, and a feature must
never be computable from date >= the game date (as-of construction).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.compose import challenger as C
from scripts.platformkit.compose.team_form import _asof_weighted_mean, prior_rows


# --------------------------------------------------------------------------- #
# as-of leak guard
# --------------------------------------------------------------------------- #
def test_prior_rows_excludes_current_and_future():
    ev = pd.DataFrame({"date": pd.to_datetime(["2025-01-01", "2025-01-05",
                                               "2025-01-10"]), "v": [1.0, 2.0, 3.0]})
    got = prior_rows(ev, pd.Timestamp("2025-01-05"))
    assert list(got["v"]) == [1.0]           # only the strictly-earlier game
    assert prior_rows(ev, pd.Timestamp("2025-01-01")).empty  # first game: no prior


def test_asof_is_strictly_prior_and_future_proof():
    # one team, three dated games; weight = 1 each
    long = pd.DataFrame({
        "game_id": ["g1", "g2", "g3"], "team": ["A", "A", "A"],
        "date": pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-03"]),
        "v": [10.0, 20.0, 30.0], "w": [1.0, 1.0, 1.0]})
    s = _asof_weighted_mean(long.rename(columns={"v": "v", "w": "w"}), "v", "w")
    assert np.isnan(s[("g1", "A")])          # no prior game -> undefined
    assert s[("g2", "A")] == 10.0            # only g1
    assert s[("g3", "A")] == 15.0            # mean(g1,g2), NOT including g3

    # mutate the FUTURE game's value; an earlier as-of must not move (no leak)
    long2 = long.copy()
    long2.loc[long2.game_id == "g3", "v"] = 999.0
    s2 = _asof_weighted_mean(long2, "v", "w")
    assert s2[("g2", "A")] == 10.0 and s2[("g3", "A")] == 15.0


# --------------------------------------------------------------------------- #
# planted-signal / pure-noise end-to-end through the composed gate
# --------------------------------------------------------------------------- #
def _synthetic(monkeypatch, planted: bool, n: int = 400, seed: int = 0):
    """Wire challenger to a synthetic team_form + neutral (zero) Elo base so the
    ONLY information available is the composed offense diff."""
    rng = np.random.default_rng(seed)
    gid = [f"S{i:04d}" for i in range(n)]
    off_diff = rng.normal(size=n)            # the offense feature-diff
    if planted:
        p = 1.0 / (1.0 + np.exp(-3.0 * off_diff))
        y = (rng.random(n) < p).astype(float)
    else:
        y = (rng.random(n) < 0.5).astype(float)  # outcome independent of features
    tf = pd.DataFrame({
        "game_id": gid, "date": pd.date_range("2025-10-01", periods=n),
        "home_team": ["H"] * n, "away_team": ["A"] * n, "home_win": y,
        "off_home": off_diff, "off_away": 0.0,
        "conc_home": 0.0, "conc_away": 0.0,
        "net_home": 0.0, "net_away": 0.0, "rest_diff": 0.0})
    games = pd.DataFrame({"game_id": gid})   # index position == row order
    base_logit = np.zeros(n)                  # neutral Elo -> features are all we have
    monkeypatch.setattr(C, "build_team_form", lambda season="2025-26": tf)
    monkeypatch.setattr(C, "_base_logit_nba", lambda: (games, base_logit))


def test_planted_signal_is_detected(monkeypatch):
    _synthetic(monkeypatch, planted=True)
    res = {r.metric: r for r in C.run_challenger()}
    off = res["+offense"]
    assert off.delta > 0 and off.dm_p < 0.05
    assert off.verdict == "MATTERS_PROVISIONAL"


def test_pure_noise_is_refused(monkeypatch):
    _synthetic(monkeypatch, planted=False)
    res = C.run_challenger()
    assert all(r.verdict == "NULL" for r in res)  # gate refuses noise
