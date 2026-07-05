# -*- coding: utf-8 -*-
"""Per-file test for scripts.platformkit.geo.soccer_altitude_gate_run.

Mirrors tests/platformkit/test_nba_travel_gate_run.py's synthetic-fixture
style (fast, no disk/corpus dependency): (1) a pure-noise column does NOT
replicate both directions -> REJECT/PARTIAL; (2) a genuinely informative
column CAN win a direction (the gate can pass); (3) a degenerate BASE ->
INVALID_BASE, never SHIP; (4) <2 corpora -> INSUFFICIENT_DATA; (5) no
$/edge field anywhere in the verdict JSON.

Per-file only: python -m pytest scripts/platformkit/geo/test_soccer_altitude_gate_run.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.geo import soccer_altitude_gate_run as G


def _corpus(n: int, year: int, *, signal: bool, skillful_base: bool,
            seed: int) -> pd.DataFrame:
    """One synthetic year corpus with a Skellam-style prob + candidate + outcome."""
    rng = np.random.default_rng(seed)
    if skillful_base:
        true_p = np.clip(rng.beta(2.0, 2.0, n), 0.05, 0.95)
        p_base = np.clip(true_p + rng.normal(0, 0.05, n), 0.02, 0.98)
    else:
        true_p = np.full(n, 0.5)
        p_base = np.full(n, 0.5) + rng.normal(0, 1e-4, n)
    y = (rng.uniform(0, 1, n) < true_p).astype(float)
    col = (y + rng.normal(0, 0.3, n)) if signal else rng.standard_normal(n)
    return pd.DataFrame({
        "date": pd.to_datetime(["%d-01-%02d" % (year, (i % 28) + 1) for i in range(n)]),
        "home_team": ["H%d" % i for i in range(n)],
        "away_team": ["A%d" % i for i in range(n)],
        "season": year, "home_win": y, "p_home_skellam": p_base, "cand": col,
    })


def _two(year_a=2010, year_b=2011, **kw):
    a = _corpus(year=year_a, seed=kw.pop("seed_a", 1), **kw)
    b = _corpus(year=year_b, seed=kw.pop("seed_b", 2), **kw)
    return [(str(year_a), a), (str(year_b), b)]


def test_planted_null_does_not_replicate():
    corpora = _two(n=500, signal=False, skillful_base=True)
    r = G.gate_one(corpora, "cand", eps=0.05)
    assert r["verdict"] in ("REJECT", "PARTIAL")
    assert r["base_degenerate"] is False


def test_gate_can_pass_a_real_signal():
    corpora = _two(n=800, signal=True, skillful_base=True)
    r = G.gate_one(corpora, "cand", eps=0.05)
    pair = r["pairs"][0]
    won = pair["a_to_b"]["feat_wins"] or pair["b_to_a"]["feat_wins"]
    assert won, "an informative column should win in >=1 direction"


def test_degenerate_base_guard():
    corpora = _two(n=500, signal=True, skillful_base=False)
    r = G.gate_one(corpora, "cand", eps=0.05)
    assert r["base_degenerate"] is True
    assert r["verdict"] == "INVALID_BASE"


def test_insufficient_data_single_corpus(monkeypatch):
    one = _corpus(n=300, year=2010, signal=True, skillful_base=True, seed=7)
    one["altitude_m"] = 100.0
    one[G._NULL_COL] = 0.0
    monkeypatch.setattr(G, "build_corpus", lambda: one)
    v = G.run()
    assert v.verdict == "INSUFFICIENT_DATA"
    assert v.n_corpora == 1


def test_no_dollar_or_edge_field(monkeypatch):
    frames = []
    for si, y in enumerate((2010, 2011)):
        c = _corpus(n=400, year=y, signal=False, skillful_base=True, seed=10 + si)
        c = c.rename(columns={"cand": "_drop"})
        c["altitude_m"] = np.abs(np.random.default_rng(si).normal(300, 200, len(c)))
        c[G._NULL_COL] = np.random.default_rng(si + 99).standard_normal(len(c))
        frames.append(c)
    feat = pd.concat(frames, ignore_index=True)
    monkeypatch.setattr(G, "build_corpus", lambda: feat)
    v = G.run()
    d = v.to_dict()
    bad_keys = ("roi", "profit", "dollar", "bankroll", "stake", "payout", "edge_")
    for k in d:
        assert not any(b in k.lower() for b in bad_keys), k
    disclaimer = " ".join(d.get("caveats", []) + [d.get("vs_close", "")]).lower()
    assert "no $" in disclaimer or "not a market edge" in disclaimer
    assert d["proposal_only"] is True
    assert "CALIBRATION" in d["vs_close"]
    assert v.null_rejects is True


def test_skellam_p_home_matches_manual_skellam_sf():
    """P(home win) via p_home_skellam must equal skellam.sf(0, lh, la) exactly
    -- this is a closed-form read-off, never a fitted estimate."""
    from scipy.stats import skellam
    lh, la = np.array([1.5, 2.0, 0.8]), np.array([1.0, 2.0, 1.9])
    got = G.p_home_skellam(lh, la)
    expected = skellam.sf(0, lh, la)
    assert np.allclose(got, expected)
