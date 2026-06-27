"""Tests for ingame_prop_dist_mlb -- engine-backed pregame lam for live players.

Offline: a fake (cfg, df, index) ctx is injected so we pin the resolve->distribute flow,
the COMPOSITE Hits+Runs+RBIs lam = sum of component lams, and the no-fabrication omissions,
without loading the real parquet/engine.
"""
from __future__ import annotations

from scripts.platformkit.bestbets.prop_settler_mlb import _norm
from scripts.platformkit.ingame import ingame_prop_dist_mlb as D


class _Cfg:
    """Minimal stand-in for SportPropConfig: name->id resolve + per-stat lam engine."""
    def __init__(self, ids, lams):
        self._ids, self._lams = ids, lams           # {name: pid}, {(pid,stat): lam}

    def resolve_player(self, df, raw, *, team, index):
        pid = self._ids.get(raw)
        if pid is None:
            return {"status": "unresolved"}
        return {"status": "ok", "player_id": pid, "matched_name": raw}

    def engine_distribution(self, df, pid, stat, as_of, **kw):
        lam = self._lams.get((pid, stat))
        if lam is None:
            return {"status": "no_data"}
        return {"status": "ok", "lam": lam, "model": "poisson", "n": 100}


def _ctx_loader(cfg):
    return lambda sport: (cfg, "DF", "INDEX")


def test_single_stat_lam():
    cfg = _Cfg({"Jacob deGrom": "p1"}, {("p1", "Pitcher Strikeouts"): 6.2})
    out = D.engine_dist_lookup("mlb", [("Jacob deGrom", "Pitcher Strikeouts")],
                               "2026-06-24", ctx_loader=_ctx_loader(cfg))
    assert out[(_norm("Jacob deGrom"), "Pitcher Strikeouts")] == (6.2, "poisson")


def test_composite_hrr_sums_components():
    cfg = _Cfg({"Wyatt Langford": "p2"},
               {("p2", "Hits"): 1.0, ("p2", "Runs"): 0.6, ("p2", "RBIs"): 0.7})
    out = D.engine_dist_lookup("mlb", [("Wyatt Langford", "Hits+Runs+RBIs")],
                               "2026-06-24", ctx_loader=_ctx_loader(cfg))
    lam, model = out[(_norm("Wyatt Langford"), "Hits+Runs+RBIs")]
    assert abs(lam - 2.3) < 1e-9 and model == "poisson"


def test_composite_missing_component_is_omitted():
    # missing the RBIs component -> never fabricate a partial sum -> omit the pair
    cfg = _Cfg({"Wyatt Langford": "p2"}, {("p2", "Hits"): 1.0, ("p2", "Runs"): 0.6})
    out = D.engine_dist_lookup("mlb", [("Wyatt Langford", "Hits+Runs+RBIs")],
                               "2026-06-24", ctx_loader=_ctx_loader(cfg))
    assert out == {}


def test_unresolved_player_omitted():
    cfg = _Cfg({}, {})
    out = D.engine_dist_lookup("mlb", [("Nobody", "Hits")], "2026-06-24",
                               ctx_loader=_ctx_loader(cfg))
    assert out == {}


def test_no_ctx_returns_empty():
    out = D.engine_dist_lookup("mlb", [("X", "Hits")], "2026-06-24",
                               ctx_loader=lambda s: None)
    assert out == {}
