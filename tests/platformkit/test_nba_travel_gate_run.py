"""Per-file test for scripts.platformkit.nba_travel_gate_run.

Asserts the HONESTY rails of the NBA pregame travel gate-run on tiny synthetic
multi-corpus fixtures (no disk dependency): (1) a pure-noise column does NOT
replicate in both cross-corpus directions -> REJECT/PARTIAL (the gate can FAIL a
signal); (2) a column genuinely tied to the outcome can win (the gate can pass);
(3) the degenerate-base guard fires when the Elo BASE is NOT skillful -> never a
SHIP; (4) <2 corpora -> INSUFFICIENT_DATA, never a fabricated win; (5) no $/edge
field anywhere in the verdict JSON. Per-file only -- never the full suite.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit import nba_travel_gate_run as G


def _corpus(n: int, season: str, *, signal: bool, skillful_base: bool,
            seed: int) -> pd.DataFrame:
    """One synthetic season corpus with an Elo prob + a candidate column + outcome.

    skillful_base=True -> p_home_elo is genuinely predictive of home_win (Elo BASE
    beats the base-rate); False -> p_home_elo is constant-ish noise (degenerate base).
    signal=True -> the candidate column is tied to the outcome; False -> pure noise.
    """
    rng = np.random.default_rng(seed)
    if skillful_base:
        true_p = np.clip(rng.beta(2.0, 2.0, n), 0.05, 0.95)
        p_elo = np.clip(true_p + rng.normal(0, 0.05, n), 0.02, 0.98)
    else:
        true_p = np.full(n, 0.5)
        p_elo = np.full(n, 0.5) + rng.normal(0, 1e-4, n)
    y = (rng.uniform(0, 1, n) < true_p).astype(float)
    col = (y + rng.normal(0, 0.3, n)) if signal else rng.standard_normal(n)
    return pd.DataFrame({
        "game_id": ["g%s_%d" % (season, i) for i in range(n)],
        "season": season, "home_win": y, "p_home_elo": p_elo, "cand": col,
    })


def _two(season_a="2022-23", season_b="2023-24", **kw):
    a = _corpus(season=season_a, seed=kw.pop("seed_a", 1), **kw)
    b = _corpus(season=season_b, seed=kw.pop("seed_b", 2), **kw)
    return [(season_a, a), (season_b, b)]


def test_planted_null_does_not_replicate():
    """A pure-noise column must NOT replicate both directions -> REJECT/PARTIAL."""
    corpora = _two(n=500, signal=False, skillful_base=True)
    r = G.gate_one(corpora, "cand", eps=0.05)
    assert r["verdict"] in ("REJECT", "PARTIAL")
    assert r["base_degenerate"] is False


def test_gate_can_pass_a_real_signal():
    """A column genuinely tied to the outcome can win a direction (gate can pass too)."""
    corpora = _two(n=800, signal=True, skillful_base=True)
    r = G.gate_one(corpora, "cand", eps=0.05)
    pair = r["pairs"][0]
    won = pair["a_to_b"]["feat_wins"] or pair["b_to_a"]["feat_wins"]
    assert won, "an informative pregame column should win in >=1 direction"


def test_degenerate_base_guard():
    """When the Elo BASE is not skillful the run is INVALID_BASE, never a SHIP."""
    corpora = _two(n=500, signal=True, skillful_base=False)
    r = G.gate_one(corpora, "cand", eps=0.05)
    assert r["base_degenerate"] is True
    assert r["verdict"] == "INVALID_BASE"


def test_insufficient_data_single_corpus(tmp_path, monkeypatch):
    """Only one season corpus -> INSUFFICIENT_DATA, never a fabricated SHIP."""
    one = _corpus(n=300, season="2022-23", signal=True, skillful_base=True, seed=7)
    # add the columns build_corpus would add, then monkeypatch build_corpus
    one["travel_home"] = 0.0
    one["travel_away"] = 100.0
    one["abs_travel_diff"] = 100.0
    one[G._NULL_COL] = 0.0
    monkeypatch.setattr(G, "build_corpus", lambda: one)
    v = G.run()
    assert v.verdict == "INSUFFICIENT_DATA"
    assert v.n_corpora == 1


def test_no_dollar_or_edge_field(monkeypatch):
    """No $/ROI/edge field anywhere; proposal_only True; vs_close UNPROVEN."""
    frames = []
    for si, s in enumerate(("2022-23", "2023-24")):
        c = _corpus(n=400, season=s, signal=False, skillful_base=True, seed=10 + si)
        c = c.rename(columns={"cand": "_drop"})
        c["travel_home"] = 0.0
        c["travel_away"] = abs(np.random.default_rng(si).normal(300, 200, len(c)))
        c["abs_travel_diff"] = c["travel_away"].abs()
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
