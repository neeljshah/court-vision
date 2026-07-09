"""Per-file tests for the attribute -> in-game conditioning prereg lane.

Covers the three things the brief names: (1) as-of/leak guard on the team-agg
prior, (2) rung-addition comparability (candidate = base + EXACTLY one column),
(3) verdict rules. No pbp IO -- all synthetic so the file runs in seconds.

    python -m pytest domains/basketball_nba/prereg/test_ingame_attribute_conditioning.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.ingame_compose.attribute_conditioning import (
    HypResult, _score_incremental,
)
from scripts.platformkit.ingame_compose.attribute_priors import (
    _rim_flag, continuity_asof, rim_allowed_asof, three_share_asof,
)
from domains.basketball_nba.prereg.ingame_attribute_conditioning import ALPHA, _verdict


# ---------------------------- (1) as-of / leak ------------------------------
def _tbl():
    return pd.DataFrame([
        {"team": "OKC", "date": pd.Timestamp("2026-01-01"), "att2": 10, "att3": 10,
         "rim": 5, "def_rim": 4, "def_tot": 20},
        {"team": "OKC", "date": pd.Timestamp("2026-01-05"), "att2": 20, "att3": 30,
         "rim": 9, "def_rim": 8, "def_tot": 40},
    ])


def test_prior_is_strictly_prior():
    t = _tbl()
    # a game ON 2026-01-05 must NOT see that day's row (date < target strict) --
    # it sees only the 2026-01-01 cumulative row.
    assert three_share_asof(t, "OKC", pd.Timestamp("2026-01-05")) == 10 / 20
    assert rim_allowed_asof(t, "OKC", pd.Timestamp("2026-01-05")) == 4 / 20
    # a game AFTER the last row sees the full cumulative row.
    assert three_share_asof(t, "OKC", pd.Timestamp("2026-02-01")) == 30 / 50
    # first-ever game for a team: no prior -> None (never imputed).
    assert three_share_asof(t, "OKC", pd.Timestamp("2025-12-01")) is None
    assert rim_allowed_asof(t, "LAL", pd.Timestamp("2026-02-01")) is None


def test_continuity_strictly_prior_and_min_history():
    a = frozenset({1, 2, 3, 4, 5})
    b = frozenset({1, 2, 3, 4, 6})       # jaccard(a,b) = 4/6
    seq = {10: [(pd.Timestamp("2026-01-01"), a),
                (pd.Timestamp("2026-01-03"), b),
                (pd.Timestamp("2026-01-05"), a)]}
    # target 2026-01-05 sees the first two only -> one consecutive pair 4/6.
    assert abs(continuity_asof(seq, 10, pd.Timestamp("2026-01-05")) - 4 / 6) < 1e-9
    # <2 prior lineups -> None (cannot measure continuity, never imputed).
    assert continuity_asof(seq, 10, pd.Timestamp("2026-01-02")) is None
    # same-date game does NOT see its own lineup (strict <).
    assert continuity_asof(seq, 10, pd.Timestamp("2026-01-03")) is None


# ---------------------------- (2) comparability -----------------------------
def _synth(term_signal: bool, seed: int = 0):
    rng = np.random.default_rng(seed)
    n = 400
    y = (rng.random(n) < 0.5).astype(float)
    if term_signal:
        term = (y - 0.5) + rng.normal(0, 0.3, n)   # informative
    else:
        term = rng.normal(0, 1, n)                 # pure noise
    feats = pd.DataFrame({"score": np.zeros(n), "term": term})
    return np.zeros(n), feats, y, np.arange(n).astype(str)


def test_informative_term_improves_brier():
    elo, feats, y, gid = _synth(term_signal=True, seed=1)
    r = _score_incremental([], "term", elo, feats, y, gid, "h", "s", "half")
    assert r.delta > 0                       # candidate beats base out-of-sample
    assert r.verdict == "MATTERS_PROVISIONAL"


def test_noise_term_is_null():
    elo, feats, y, gid = _synth(term_signal=False, seed=2)
    r = _score_incremental([], "term", elo, feats, y, gid, "h", "s", "half")
    assert r.verdict == "NULL"               # no honest lift from noise


def test_base_cols_run_and_add_one_column():
    # with a base survivor column present, the gate still fits (base = intercept
    # + score + star_minutes_load; candidate adds EXACTLY term).
    elo, feats, y, gid = _synth(term_signal=True, seed=3)
    feats["star_minutes_load"] = np.zeros(len(y))
    r = _score_incremental(["star_minutes_load"], "term", elo, feats, y, gid, "h", "s", "endQ1")
    assert r.n_test > 0 and r.delta > 0


# ------------------------------ (3) verdicts --------------------------------
def test_verdict_rules():
    survive = HypResult("h", "s", "half", 100, 0.001, 0.001, ALPHA / 2, "x")
    assert _verdict(survive) == "SURVIVES_PREREG"
    # significant but delta_trunc80 <= 0 -> not robust -> NULL
    unstable = HypResult("h", "s", "half", 100, 0.001, -0.001, ALPHA / 2, "x")
    assert _verdict(unstable) == "NULL"
    # p above the Bonferroni bar -> NULL even with positive delta
    weak = HypResult("h", "s", "half", 100, 0.001, 0.001, ALPHA * 2, "x")
    assert _verdict(weak) == "NULL"
    # never scored -> NOT_TESTABLE, not FAILED
    assert _verdict(HypResult("h", "s", "half", 0, 0.0, 0.0, 1.0, "NOT_TESTABLE")) == "NOT_TESTABLE"


def test_rim_flag():
    assert _rim_flag({"actionType": "2pt", "description": "makes 2-foot dunk"})
    assert _rim_flag({"actionType": "2pt", "description": "makes driving layup"})
    assert not _rim_flag({"actionType": "2pt", "description": "makes 18-foot jumper"})
    assert not _rim_flag({"actionType": "3pt", "description": "makes 26-foot three"})


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
