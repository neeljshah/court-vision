"""Fast unit tests for the V7 paper sportsbook engine (gated CV_SPORTSBOOK_ENGINE).

Uses a STUBBED sim result (np-generated samples, no GPU/cache) so the whole suite
runs in well under 30s.  Asserts:
  - importing the module is byte-side-effect-free (no sim, no prints)
  - the ontology prices >= 100 concrete market types from a small stub
  - the portfolio optimizer returns a list (empty allowed; honest empty w/o lines)
  - SGP joint vs product-of-marginals returns sane probabilities + correct sign
    on the negatively-correlated teammate basket
  - the engine never touches the real-money path (no bet_log mutation)
"""
import importlib
import os
import sys
import types

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "team_system"))
sys.path.insert(0, os.path.join(ROOT, "src"))

# market_catalog / portfolio_optimizer import prop_engine which imports the sim +
# availability; those import cleanly even without the cache, so module import is safe.
import market_catalog as mc          # noqa: E402
import portfolio_optimizer as po     # noqa: E402
import sportsbook_engine as sbe       # noqa: E402
from sim.sgp_from_sim import Leg, joint_prob  # noqa: E402


# ---------------------------------------------------------------------------
# A tiny self-contained stub sim result (no cache, no GPU)
# ---------------------------------------------------------------------------

_ALL_KEYS = ["pts", "fga", "fgm", "fg3a", "fg3m", "fta", "ftm",
             "oreb", "dreb", "ast", "stl", "blk", "tov", "pf", "reb"]


def _player(rng, pts_mean, reb_mean, ast_mean, name, team, pool, pie_sign=0.0):
    """Build one player's joint samples.

    `pie_sign` (+1 / -1) shifts pts by a SHARED team driver `pool` with opposite
    signs for two teammates -> when one scores more the other scores less (a shared
    scoring pie -> negative teammate pts-pts correlation, like the real sim)."""
    n = pool.shape[0]
    pts = np.clip(
        rng.normal(pts_mean, pts_mean * 0.18, n) + pie_sign * (pool - pool.mean()),
        0, None,
    )
    reb = np.clip(rng.normal(reb_mean, max(reb_mean * 0.4, 1.0), n), 0, None)
    ast = np.clip(rng.normal(ast_mean, max(ast_mean * 0.5, 1.0), n), 0, None)
    s = {
        "pts": pts, "reb": reb, "ast": ast,
        "fga": pts * 0.9, "fgm": pts * 0.4, "fg3a": pts * 0.25, "fg3m": pts * 0.1,
        "fta": pts * 0.3, "ftm": pts * 0.25,
        "oreb": reb * 0.3, "dreb": reb * 0.7,
        "stl": rng.poisson(1.0, n).astype(float), "blk": rng.poisson(0.6, n).astype(float),
        "tov": rng.poisson(2.0, n).astype(float), "pf": rng.poisson(2.2, n).astype(float),
    }
    return {"name": name, "team": team,
            "mean": {"pts": float(pts.mean()), "reb": float(reb.mean()), "ast": float(ast.mean())},
            "reb_mean": float(reb.mean()),
            "samples": {k: s[k] for k in _ALL_KEYS}}


def _stub_result(n=4000, seed=1):
    rng = np.random.default_rng(seed)
    pool = rng.normal(0, 6, n)   # shared scoring-pie driver
    # Teammates 101/102 get OPPOSITE signs of the shared pie -> when one is up the
    # other is down -> negative empirical teammate pts-pts correlation.
    players = {
        101: _player(rng, 26, 4, 7, "Star Guard", "NYK", pool, pie_sign=+1.0),
        102: _player(rng, 20, 11, 3, "Big Man", "NYK", pool, pie_sign=-1.0),
        103: _player(rng, 14, 5, 4, "Wing", "NYK", pool),
        201: _player(rng, 24, 10, 4, "Away Star", "SAS", -pool, pie_sign=+1.0),
        202: _player(rng, 13, 6, 5, "Away Wing", "SAS", -pool, pie_sign=-1.0),
    }
    home_total = sum(players[p]["samples"]["pts"] for p in (101, 102, 103)) + rng.normal(50, 6, n)
    away_total = sum(players[p]["samples"]["pts"] for p in (201, 202)) + rng.normal(70, 6, n)
    return types.SimpleNamespace(
        home_tri="NYK", away_tri="SAS",
        home_total=home_total, away_total=away_total,
        home_win_prob=float((home_total > away_total).mean()),
        players=players,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_import_is_side_effect_free(capsys):
    """Re-importing the module runs no sim and prints nothing."""
    importlib.reload(sbe)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert hasattr(sbe, "run_engine") and hasattr(sbe, "main")


def test_gate_default_off(monkeypatch, capsys):
    """With the flag unset and no --demo, main() is a no-op."""
    monkeypatch.delenv("CV_SPORTSBOOK_ENGINE", raising=False)
    assert sbe.is_enabled(force=False) is False
    rc = sbe.main(["--home", "NYK", "--away", "SAS", "--nsims", "10"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "disabled (no-op)" in out


def test_gate_enabled_by_env_or_demo(monkeypatch):
    monkeypatch.setenv("CV_SPORTSBOOK_ENGINE", "1")
    assert sbe.is_enabled(force=False) is True
    monkeypatch.setenv("CV_SPORTSBOOK_ENGINE", "0")
    assert sbe.is_enabled(force=False) is False
    assert sbe.is_enabled(force=True) is True   # --demo forces on


def test_ontology_prices_over_100_market_types():
    res = _stub_result()
    n = mc.ontology_count(res)
    assert n >= 100, f"ontology_count {n} < 100"
    markets = mc.price_markets(res)
    assert len(markets) >= 100, f"priced {len(markets)} < 100"
    # distinct market TYPES (not just instances)
    assert len({m["market_type"] for m in markets}) >= 8
    # every priced market is paper honesty
    assert {m["honesty_class"] for m in markets} == {"paper"}


def test_portfolio_returns_list_empty_when_no_lines():
    res = _stub_result()
    markets = mc.price_markets(res)  # no paper_lines -> all edge=None
    port = po.build_portfolio(res, markets)
    assert isinstance(port["bets"], list)
    assert port["bets"] == []                 # honest empty: no book lines => not bettable
    assert port["n_candidates"] == 0
    assert port["honesty_class"] == "paper"
    assert "no real-money path" in port["caveat"].lower() or "PAPER" in port["caveat"]


def test_portfolio_nonempty_with_synth_lines():
    res = _stub_result()
    lines = sbe.synth_paper_lines(res)
    assert len(lines) > 0
    markets = mc.price_markets(res, lines)
    port = po.build_portfolio(res, markets, min_edge=0.02)
    assert isinstance(port["bets"], list)
    # synth lines shade the over to value -> at least one +EV candidate
    assert len(port["bets"]) >= 1
    for b in port["bets"]:
        assert 0.0 <= b["model_prob"] <= 1.0
        assert b["stake"] >= 0.0
        assert b["edge"] >= 0.02


def test_sgp_joint_vs_product_sane_and_negative_teammate_corr():
    res = _stub_result()
    # same-player pts & reb (both at median -> ~0.5 each)
    p = 101
    line_pts = float(np.median(res.players[p]["samples"]["pts"]))
    line_reb = float(np.median(res.players[p]["samples"]["reb"]))
    j, ind, lift = joint_prob(res, [Leg(p, "pts", line_pts), Leg(p, "reb", line_reb)])
    assert 0.0 <= j <= 1.0 and 0.0 <= ind <= 1.0
    assert j <= max(0.5, ind) + 0.05   # joint never exceeds the smaller marginal by much

    # teammates pts & pts share the pie -> negative correlation -> lift < 1
    l1 = float(np.median(res.players[101]["samples"]["pts"]))
    l2 = float(np.median(res.players[102]["samples"]["pts"]))
    j2, ind2, lift2 = joint_prob(res, [Leg(101, "pts", l1), Leg(102, "pts", l2)])
    assert lift2 < 1.0, f"teammate lift {lift2} should be <1 (negative corr)"


def test_run_engine_demo_path():
    """The integrator's run_engine composes catalog + sgp + portfolio on a stub.

    We monkeypatch prop_engine.run to return the stub so no GPU/cache is needed.
    """
    import prop_engine
    res = _stub_result()
    orig = prop_engine.run
    prop_engine.run = lambda *a, **k: res
    try:
        out = sbe.run_engine(home="NYK", away="SAS", nsims=10, demo=True)
    finally:
        prop_engine.run = orig
    assert out["n_concrete"] >= 100
    assert out["honesty_class"] == "paper"
    assert len(out["sgp"]) >= 2
    assert isinstance(out["portfolio"]["bets"], list)
    # demo synthesized paper lines -> portfolio should have candidates
    assert out["paper_lines"] is not None


def test_no_real_money_path():
    """The engine never CALLS log_bet / record_clv and never writes bet_log.json.

    (Those names may appear in the docstring describing what the engine does NOT do;
    the guarantee is that they are never invoked / no log file is opened for write.)"""
    src = open(os.path.join(ROOT, "scripts", "team_system", "sportsbook_engine.py"),
               encoding="utf-8").read()
    assert "log_bet(" not in src
    assert "record_clv(" not in src
    assert "bet_log.json" not in src.replace(
        "no log_bet / record_clv / bet_log.json", "")  # ignore the docstring mention
    # portfolio_optimizer (the only thing that sizes stakes) must not touch them either
    po_src = open(os.path.join(ROOT, "scripts", "team_system", "portfolio_optimizer.py"),
                  encoding="utf-8").read()
    assert "log_bet(" not in po_src and "record_clv(" not in po_src


def test_sample_covariance_is_empirical():
    """Correlation matrix comes from the joint samples (teammate pts negatively
    correlated)."""
    res = _stub_result()
    markets = [
        {"market_type": "pts_ou", "entity": "101", "stat": "pts", "side": "over",
         "line": float(np.median(res.players[101]["samples"]["pts"]))},
        {"market_type": "pts_ou", "entity": "102", "stat": "pts", "side": "over",
         "line": float(np.median(res.players[102]["samples"]["pts"]))},
    ]
    corr, kept = po.sample_covariance(res, markets)
    assert len(kept) == 2
    assert corr.shape == (2, 2)
    assert corr[0, 1] < 0.0   # shared-pie teammates -> negative empirical corr


def test_model_prob_evaluated_at_book_line():
    """Apples-to-apples fix: when a book line is supplied, model_prob is P(stat vs book line)
    from the joint samples — NOT P(stat vs sim-median line).

    Regression: before the fix, model_prob was always computed at _qline(arr) (sim median),
    so a book line shifted 2 sigma away would still show ~0.50 model_prob, making edge
    meaningless. After the fix, a far-OTM book OVER has a low model_prob (<0.20) and a
    far-ITM book OVER has a high model_prob (>0.80).
    """
    res = _stub_result()
    pid = 101   # Star Guard, pts_mean≈26
    pts_samples = np.asarray(res.players[pid]["samples"]["pts"], float)
    pts_median = float(np.median(pts_samples))

    # Supply a paper_lines entry with a far-OTM line (median + 2*std ~ very high)
    pts_std = float(pts_samples.std())
    far_otm_line = round((pts_median + 2.0 * pts_std) * 2) / 2  # snap to .5

    paper_lines_otm = {
        f"101|pts_ou": {
            "line": far_otm_line,
            "over_odds": 300,   # book prices it as a longshot
            "under_odds": -400,
        }
    }
    markets_otm = mc.price_markets(res, paper_lines_otm)
    # Find the pts_ou over row for player 101
    row = next(m for m in markets_otm
               if m["entity"] == "101" and m["market_type"] == "pts_ou" and m["side"] == "over")

    # model_prob should be low (far-OTM line) — apples-to-apples
    assert row["model_prob"] < 0.20, (
        f"Far-OTM over should have model_prob<0.20; got {row['model_prob']:.3f} "
        f"(line={row['line']}, fair_line≈{pts_median:.1f}). "
        "model_prob was evaluated at sim median instead of book line (regression)."
    )
    # edge and ev should be populated and internally consistent:
    # model_prob(at book line) - devig_implied(at book line)
    assert row["book_prob"] is not None and row["edge"] is not None
    assert abs(row["edge"] - (row["model_prob"] - row["book_prob"])) < 1e-9

    # Symmetric check: supply a far-ITM line (very low bar)
    far_itm_line = max(0.5, round((pts_median - 2.0 * pts_std) * 2) / 2)
    paper_lines_itm = {
        f"101|pts_ou": {
            "line": far_itm_line,
            "over_odds": -800,  # book prices it as a heavy favourite
            "under_odds": 500,
        }
    }
    markets_itm = mc.price_markets(res, paper_lines_itm)
    row_itm = next(m for m in markets_itm
                   if m["entity"] == "101" and m["market_type"] == "pts_ou" and m["side"] == "over")
    assert row_itm["model_prob"] > 0.80, (
        f"Far-ITM over should have model_prob>0.80; got {row_itm['model_prob']:.3f} "
        f"(line={row_itm['line']}, fair_line≈{pts_median:.1f})."
    )

    # Backward-compat: no paper_lines -> model_prob should be ~0.50 (at sim median)
    markets_no_lines = mc.price_markets(res, None)
    row_no = next(m for m in markets_no_lines
                  if m["entity"] == "101" and m["market_type"] == "pts_ou" and m["side"] == "over")
    assert 0.45 <= row_no["model_prob"] <= 0.55, (
        f"No-book-line: pts_ou over model_prob should be ~0.50 (at sim median); "
        f"got {row_no['model_prob']:.3f}."
    )
