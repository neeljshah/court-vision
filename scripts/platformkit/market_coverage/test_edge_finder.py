"""Per-file tests for market_coverage.edge_finder -- the OBSCURE-MARKET edge HUNTER.

Run ONLY this file:
  cd /c/Users/neelj/nba-ai-system && \
  C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest \
  scripts/platformkit/market_coverage/tests/test_edge_finder.py -q

Guards the HONEST RAILS through the REAL eval gate (reused read-only):
  - a PLANTED mispriced (soft-close) market is FOUND -> SHIP, and ALWAYS flagged
    needs-forward-CLV (a soft-line beat is SUGGESTIVE, never a $ claim);
  - an EFFICIENT mainline (model priced AT the devigged close) REJECTs / MATCHes
    -> no fabricated survivor;
  - the leak guard (walk_forward.assert_vintage) FIRES on a leaked feature;
  - obscure markets with no local close are NEEDS_FORWARD_CLV (cannot ship here);
  - the >=2-corpora rule blocks a single-fold lift.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from scripts.platformkit.market_coverage import edge_finder as EF  # noqa: E402
# the gate's leak guard, reused read-only -- we assert it fires.
from scripts.platformkit.eval_gate.walkforward import walk_forward, assert_vintage  # noqa: E402


def _ts(i: int) -> str:
    """Distinct ISO timestamp per game so walk_forward orders them and the purge /
    embargo never collapse the sample (each a unique matchup, days apart)."""
    return (datetime(2026, 1, 1) + timedelta(days=i)).isoformat()


def _corpus(tmp_path, name):
    """A throwaway corpus dir carrying the odds.parquet sentinel evaluate_market checks
    for. The builder ignores the dir contents (it returns synthetic states), so an empty
    sentinel file is enough to let the gate run on the planted states."""
    d = tmp_path / name
    d.mkdir()
    (d / "odds.parquet").write_bytes(b"")        # sentinel only -- builder ignores it
    return d


def _states(n, true_prob_fn, close_fn, seed=0, tag=""):
    """n leak-free per-game states. true_prob_fn(i)->P(home win); the outcome is drawn
    from it; close_fn(i)->the devigged close prob. Each game a unique matchup. `tag`
    namespaces the game_id/team so pooled corpora don't merge DM clusters."""
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        tp = float(np.clip(true_prob_fn(i), 1e-3, 1 - 1e-3))
        out.append({
            "game_id": f"{tag}g{i}", "home": f"{tag}H{i}", "away": f"{tag}A{i}",
            "state_ts": _ts(i), "outcome": int(rng.uniform() < tp),
            "devig_close_prob": float(np.clip(close_fn(i), 1e-3, 1 - 1e-3)),
            "parity": i % 2,          # the planted, leak-free signal the soft close ignores
        })
    return out


# ---------------------------------------------------------------------------
# 1. PLANTED mispricing IS found through the real gate.
# ---------------------------------------------------------------------------
def test_planted_soft_line_is_found_and_flagged_forward_clv(tmp_path):
    """SOFT close = base rate 0.5 while the truth varies with i: a model that knows the
    truth beats the soft line. Drive the gate via a builder that returns these states
    and a predict_fn that conditions toward the (planted-knowable) signal."""
    n = 400
    truth = lambda i: 0.20 + 0.60 * (i % 2)        # alternating 0.20 / 0.80 -- knowable
    close = lambda i: 0.50                          # SOFT: pinned at the base rate

    def builder(root):
        return _states(n, truth, close, seed=1, tag=Path(root).name + "-")

    # a predict_fn that reads the (leak-free) train-slice signal: home-win rate of
    # same-parity past games approximates the planted truth -> beats the soft close.
    def predict_fn(train, test, select_inside):
        par = test["parity"]
        same = [t["outcome"] for t in train if t["parity"] == par]
        if not same:
            return float(test["devig_close_prob"])
        return float(np.clip(np.mean(same), 1e-3, 1 - 1e-3))

    spec = EF.MarketSpec("planted_soft", "player-props-core", "nba", True, builder)
    corpora = {"nba": _corpus(tmp_path, "c1"), "nba2": _corpus(tmp_path, "c2")}
    # monkeypatch the gate's predict_fn for this market via evaluate_market's internals:
    orig = EF._shrink_to_close_predict
    EF._shrink_to_close_predict = predict_fn
    try:
        res = EF.evaluate_market(spec, corpora)
    finally:
        EF._shrink_to_close_predict = orig
    assert res.verdict == "SHIP", (res.verdict, res.bss, res.dm_p, res.n_corpora)
    assert res.bss > EF.MATCH_BSS and res.dm_p < EF.ALPHA
    assert res.n_corpora >= EF.MIN_CORPORA           # >=2 corpora rule satisfied
    assert res.needs_forward_clv                     # SUGGESTIVE -> needs forward CLV, not $


# ---------------------------------------------------------------------------
# 2. An EFFICIENT mainline does NOT ship (no fabricated survivor).
# ---------------------------------------------------------------------------
def test_efficient_mainline_rejects(tmp_path):
    """Model priced AT the devigged close (the efficient-mainline null) -> MATCH/REJECT,
    never SHIP. The close itself is the truth here, so we cannot beat it."""
    n = 320
    truth = lambda i: 0.45 + 0.10 * np.sin(i)       # genuinely varying truth
    close = truth                                    # SHARP close == truth

    def builder(_root):
        return _states(n, truth, close, seed=2)

    def predict_fn(train, test, select_inside):      # price exactly at the close
        return float(test["devig_close_prob"])

    spec = EF.MarketSpec("efficient_ml", "mlb-soccer-tennis", "nba", True, builder)
    corpora = {"nba": _corpus(tmp_path, "c1"), "nba2": _corpus(tmp_path, "c2")}
    orig = EF._shrink_to_close_predict
    EF._shrink_to_close_predict = predict_fn
    try:
        res = EF.evaluate_market(spec, corpora)
    finally:
        EF._shrink_to_close_predict = orig
    assert res.verdict in ("MATCH", "REJECT")
    assert res.verdict != "SHIP"
    assert not res.needs_forward_clv


# ---------------------------------------------------------------------------
# 3. The leak guard FIRES on a leaked feature (reused gate machinery).
# ---------------------------------------------------------------------------
def test_leak_guard_fires():
    """A feature whose availability is NOT strictly before the prediction time must
    trip the gate's vintage assertion -- the leak-free contract is enforced, not assumed."""
    leaked = {
        "game_id": "gx", "home": "H", "away": "A", "state_ts": _ts(5),
        "outcome": 1, "devig_close_prob": 0.5,
        # availability == state_ts -> NOT strictly before -> LEAK.
        "feature_avail": {"signal": _ts(5)},
    }
    with pytest.raises(AssertionError) as e:
        assert_vintage(leaked)
    assert "LEAK" in str(e.value)

    # and through the full walk_forward path the same leak trips it.
    def predict_fn(train, test, select_inside):
        return 0.5
    with pytest.raises(AssertionError):
        walk_forward([leaked], predict_fn, select_inside=True)


# ---------------------------------------------------------------------------
# 4. Obscure no-close markets are NEEDS_FORWARD_CLV (cannot ship here).
# ---------------------------------------------------------------------------
def test_no_close_market_is_needs_forward_clv():
    spec = EF.MarketSpec("player_pts_ou", "player-props-core", "nba", has_close=False)
    res = EF.evaluate_market(spec, {})
    assert res.verdict == "NEEDS_FORWARD_CLV"
    assert res.needs_forward_clv
    assert res.n == 0                                 # never gated, never shipped


def test_enumeration_spans_all_seven_buckets_and_mostly_forward_only():
    specs = EF.enumerate_markets()
    buckets = {s.bucket for s in specs}
    assert set(EF.BUCKETS) <= buckets
    # the honest census: the obscure lane (no local close) dominates.
    no_close = [s for s in specs if not s.has_close]
    assert len(no_close) > len(specs) // 2


# ---------------------------------------------------------------------------
# 5. The >=2-corpora rule blocks a single-fold lift.
# ---------------------------------------------------------------------------
def test_single_corpus_lift_is_not_a_ship(tmp_path):
    """Even a real soft-line beat from ONE corpus must NOT ship: a single-fold lift is
    an artifact (MIN_CORPORA>=2). Provide only one corpus root -> at most 1 fold."""
    n = 400
    truth = lambda i: 0.20 + 0.60 * (i % 2)
    close = lambda i: 0.50

    def builder(root):
        return _states(n, truth, close, seed=3, tag=Path(root).name + "-")

    def predict_fn(train, test, select_inside):
        par = test["parity"]
        same = [t["outcome"] for t in train if t["parity"] == par]
        return float(np.clip(np.mean(same), 1e-3, 1 - 1e-3)) if same else 0.5

    spec = EF.MarketSpec("planted_single", "player-props-core", "nba", True, builder)
    orig = EF._shrink_to_close_predict
    EF._shrink_to_close_predict = predict_fn
    try:
        res = EF.evaluate_market(spec, {"nba": _corpus(tmp_path, "only")})   # ONE corpus
    finally:
        EF._shrink_to_close_predict = orig
    assert res.n_corpora < EF.MIN_CORPORA
    assert res.verdict != "SHIP"                      # blocked by the >=2-corpora rule


def test_no_dollar_claim_in_results():
    spec = EF.MarketSpec("x", "ingame-micro", "nba", has_close=False)
    res = EF.evaluate_market(spec, {})
    blob = (res.reason + " " + res.verdict).lower()
    for bad in ("roi", "+ev", "guaranteed", "profit"):
        assert bad not in blob
