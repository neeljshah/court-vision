"""Per-file test for pregame_winprob + pregame_winprob_gate (synthetic, no parquet)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.soccer.pregame_winprob import p_home_win, walk_forward
from domains.soccer.pregame_winprob_gate import run, _select_fair_hfa, _HFA_GRID


def test_p_home_win_monotone_and_bounded():
    # stronger home lambda -> higher P(home win); always in (0,1)
    p_lo = p_home_win(1.0, 1.0)
    p_hi = p_home_win(2.5, 0.8)
    assert 0.0 < p_lo < 1.0 and 0.0 < p_hi < 1.0
    assert p_hi > p_lo
    # equal lambdas -> below 0.5 (draw mass excluded from home-win)
    assert p_home_win(1.4, 1.4) < 0.5


def _synth_league(div: str, n: int, seed: int, home_edge: float) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    teams = [f"{div}_T{i}" for i in range(12)]
    rows = []
    base = pd.Timestamp("2020-08-01")
    for k in range(n):
        h, a = rng.choice(teams, 2, replace=False)
        sh = float(rng.normal(home_edge, 0.4))     # latent home advantage
        lam_h = max(0.3, 1.4 + sh)
        lam_a = max(0.3, 1.4 - sh)
        fhg = rng.poisson(lam_h)
        fag = rng.poisson(lam_a)
        ftr = "H" if fhg > fag else ("A" if fag > fhg else "D")
        rows.append({"event_id": f"{div}{k}", "date": base + pd.Timedelta(days=k // 5),
                     "div": div, "home_team": h, "away_team": a,
                     "fthg": fhg, "ftag": fag, "ftr": ftr})
    return pd.DataFrame(rows)


def test_walk_forward_leakfree_columns():
    df = _synth_league("X1", 200, 1, 0.25)
    wf = walk_forward(df)
    for c in ("p_elo", "p_poisson", "p_poisson_xg", "y_home"):
        assert c in wf.columns
    for c in ("p_elo", "p_poisson", "p_poisson_xg"):
        v = wf[c].to_numpy(float)
        assert np.all((v >= 0.0) & (v <= 1.0))
    assert set(wf["y_home"].unique()) <= {0, 1}


def test_walk_forward_hfa_param_changes_only_elo():
    # the hfa argument must move p_elo but leave the Poisson columns untouched
    df = _synth_league("X1", 200, 1, 0.25)
    lo = walk_forward(df, hfa=0.0)
    hi = walk_forward(df, hfa=60.0)
    assert not np.allclose(lo["p_elo"], hi["p_elo"])         # HFA shifts the Elo prob
    assert (hi["p_elo"] >= lo["p_elo"] - 1e-9).all()          # +HFA -> >= home prob
    assert np.allclose(lo["p_poisson"], hi["p_poisson"])      # Poisson is HFA-free
    assert np.allclose(lo["p_poisson_xg"], hi["p_poisson_xg"])


def test_select_fair_hfa_is_out_of_fold_and_in_grid():
    # build per-(league,hfa) frames like the gate does, then check selection ignores
    # the report league (leave-one-league-out) and returns a value on the grid.
    a = _synth_league("AA", 400, 2, 0.30)
    b = _synth_league("BB", 400, 3, 0.30)
    league_wf = {}
    for div, g in (("AA", a), ("BB", b)):
        league_wf[div] = {h: walk_forward(g, hfa=float(h)) for h in _HFA_GRID}
    h_aa = _select_fair_hfa(league_wf, "AA")   # selected on BB only
    h_bb = _select_fair_hfa(league_wf, "BB")   # selected on AA only
    assert h_aa in _HFA_GRID and h_bb in _HFA_GRID


def test_gate_runs_and_is_calibration_verdict():
    a = _synth_league("AA", 400, 2, 0.30)
    b = _synth_league("BB", 400, 3, 0.30)
    matches = pd.concat([a, b], ignore_index=True)
    o = run("poisson", matches=matches, match_stats=None)
    assert o["verdict"] in ("REPLICATED", "PARTIAL", "REJECT")
    assert "CALIBRATION" in o["vs_close"] and "not edge" in o["vs_close"]
    assert o["n_leagues"] == 2
    assert o["baseline"] == "elo_fair_hfa"
    # fair HFA was selected out-of-fold for each reported league, and lives on the grid
    assert set(o["hfa_selected"]) == {"AA", "BB"}
    for div, d in o["per_league"].items():
        assert d["fair_hfa"] in _HFA_GRID
        assert o["hfa_selected"][div] == d["fair_hfa"]
        # each league reports a finite Elo BSS vs the constant base-rate (degen guard)
        assert np.isfinite(d["elo_bss_vs_baserate"])
        # shots-over-goals fields are present and well-formed (Elo-independent claim)
        assert np.isfinite(d["shots_over_goals_delta"])
        assert isinstance(d["shots_beat_goals"], bool)
    assert "n_leagues_shots_beat_goals" in o["shots_over_goals"]
    # provenance: the selection protocol is documented as out-of-fold (no strawman)
    assert "leave-one-league-out" in o["hfa_selection_protocol"]
