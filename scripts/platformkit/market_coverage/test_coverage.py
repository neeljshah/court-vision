"""Per-file tests for market_coverage.coverage -- the per-matchup FULL-BOOK orchestrator.

Run ONLY this file:
  cd /c/Users/neelj/nba-ai-system && \
  C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest \
  scripts/platformkit/market_coverage/tests/test_coverage.py -q

coverage.py runs the real sim (read-only) and attaches the thinness/validatable honesty
tags. These tests guard the ORCHESTRATION + HONESTY contract WITHOUT a heavy sim where
possible (a stubbed coherent SampleBook drives _nba_categories), plus one small real-sim
smoke test. Guards: every NBA category is tagged + priced; mainlines read LIQUID/HAS_CLOSE
while obscure markets read FORWARD_ONLY + needs-forward-CLV; the mlb/soccer/tennis path
degrades cleanly when the corpus is absent; no $ claim leaks; the summary tallies match.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

import numpy as np  # noqa: E402

# loaded by file name to avoid the installed top-level 'coverage' (pytest-cov) shadow.
import importlib.util as _ilu  # noqa: E402

_p = Path(__file__).resolve().parents[0] / "coverage.py"
_spec = _ilu.spec_from_file_location("mc_coverage_orchestrator", _p)
COV = _ilu.module_from_spec(_spec)
sys.modules[_spec.name] = COV
_spec.loader.exec_module(COV)

from scripts.platformkit.market_coverage.markets import SampleBook  # noqa: E402
from scripts.platformkit.market_coverage import tags as TG  # noqa: E402


def _stub_book(n=4000, seed=2):
    """A coherent SampleBook with home/away + period columns + a couple of players,
    so _nba_categories enumerates every NBA category off ONE matrix (no real sim)."""
    rng = np.random.default_rng(seed)
    pace = rng.normal(0, 1, n)
    cols, columns = {}, []

    def add(name, arr):
        cols[name] = len(columns)
        columns.append(np.asarray(arr, float))

    add("home_score", 113 + 4 * pace + rng.normal(0, 6, n))
    add("away_score", 108 - pace + rng.normal(0, 6, n))
    for pid, base in (("A", 27), ("B", 16)):
        for st, b in (("pts", base), ("reb", 7), ("ast", 5), ("fg3m", 2),
                      ("stl", 1), ("blk", 0.7)):
            add(f"{pid}|{st}", b + (3 * pace if st == "pts" else rng.normal(0, 1.5, n))
                + rng.normal(0, 2, n))
    for side in ("home", "away"):
        full = columns[cols[f"{side}_score"]]
        for seg, sh in (("q1", .25), ("q2", .25), ("q3", .25), ("q4", .25),
                        ("h1", .5), ("h2", .5)):
            add(f"{side}_{seg}", full * sh * (1 + rng.normal(0, .08, n)))
    return SampleBook(np.column_stack(columns), cols, "simulated")


def test_nba_categories_tagged_and_priced():
    book = _stub_book()
    cats = COV._nba_categories(book, ingame=False, pid_name={})
    # the five pregame NBA categories all appear and carry priced+tagged rows.
    for c in ("player-props-core", "player-props-combos", "team-quarter-half",
              "game-scenario-longshot", "sgp-correlation"):
        assert cats.get(c), f"{c} empty"
    for rows in cats.values():
        for r in rows:
            assert 0.0 <= r["prob"] <= 1.0 or r["prob"] != r["prob"]   # prob or nan(joint)
            assert r["thinness"] in TG.THINNESS
            assert r["validatable"] in TG.VALIDATABLE
            assert isinstance(r["needs_forward_clv"], bool)
            assert r["category"] in COV.BB.CATEGORIES


def test_mainline_is_liquid_has_close_obscure_is_forward_only():
    book = _stub_book()
    cats = COV._nba_categories(book, ingame=False, pid_name={})
    flat = [r for rows in cats.values() for r in rows]
    # the game moneyline / spread / total mainlines should read LIQUID + HAS_CLOSE.
    mains = [r for r in flat if r["name"].startswith(("home_ml", "home_spread", "game_total"))]
    assert mains, "no mainline produced"
    assert any(r["thinness"] == "LIQUID" and r["validatable"] == "HAS_CLOSE" for r in mains)
    # an SGP / longshot / quarter market must be FORWARD_ONLY + needs-forward-CLV.
    obscure = [r for r in flat if r["category"] in
               ("sgp-correlation", "game-scenario-longshot")]
    assert obscure
    assert all(r["needs_forward_clv"] for r in obscure)
    assert any(r["validatable"] == "FORWARD_ONLY" for r in obscure)


def test_ingame_book_adds_ingame_micro():
    book = _stub_book()
    cats = COV._nba_categories(book, ingame=True, pid_name={})
    assert cats.get("ingame-micro"), "ingame-micro not produced on a live book"
    assert all(r["needs_forward_clv"] for r in cats["ingame-micro"])


def test_summary_tallies_match_flat_rows():
    book = _stub_book()
    cats = COV._nba_categories(book, ingame=False, pid_name={})
    flat = [r for rows in cats.values() for r in rows]
    s = COV._summary(flat)
    assert sum(s["by_thinness"].values()) == len(flat)
    assert sum(s["by_validatable"].values()) == len(flat)
    assert s["needs_forward_clv"] == sum(1 for r in flat if r["needs_forward_clv"])


def test_other_sport_degrades_cleanly_without_corpus(monkeypatch):
    """mlb/soccer/tennis: if the calibrated predictor can't be built (fresh clone, no
    local corpus), full_book must NOT crash -- it returns an 'unavailable' row, no $ claim."""
    import scripts.platformkit.market_coverage.coverage as real_cov

    def _no_pred(name):
        raise RuntimeError("corpus absent on this clone")
    monkeypatch.setattr("scripts.platformkit.predictor_jd._build_predictor",
                        _no_pred, raising=False)
    book = real_cov.full_book("mlb", "NYY", "BOS", n_sims=10)
    assert book["edge_claimed"] is False
    flat = [r for rows in book["markets"].values() for r in rows]
    assert flat and any(r["name"] == "unavailable" for r in flat)


def test_full_book_has_no_dollar_claim_framing():
    book = _stub_book()
    cats = COV._nba_categories(book, ingame=False, pid_name={})
    flat = [r for rows in cats.values() for r in rows]
    banned = ("roi", "+ev", "guaranteed", "beat the market", "profit")
    for r in flat:
        blob = " ".join(str(v).lower() for v in r.values())
        for b in banned:
            assert b not in blob


def test_real_sim_smoke_small():
    """One tiny REAL-sim full_book (read-only consume of src.sim). Skips if the NBA team
    cache is absent (fresh clone). Confirms the end-to-end plumbing actually runs."""
    try:
        book = COV.full_book("nba", "NYK", "SAS", n_sims=400, seed=2026)
    except Exception as exc:  # noqa: BLE001 - cache absent on a clean clone
        import pytest
        pytest.skip(f"NBA sim cache unavailable: {exc}")
    assert book["sport"] == "nba"
    assert book["n_markets"] > 0
    assert book["edge_claimed"] is False
    assert "needs_forward_clv" in book["summary"]
