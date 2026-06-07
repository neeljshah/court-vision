"""tests/test_serve_path_plumbing.py — serve-path plumbing wiring (gated, byte-identical OFF).

Covers the two gated fixes that plumb validated wins into the WEBPAGE serve path:

  1. CV_BET_POLICY on the webpage bet surface (api.courtvision_router._apply_calibration_gate):
     - OFF (iter57 default)  -> byte-identical: the same bets survive the page's existing
       Iter-57 selection stack.
     - ON  (reb_ast)         -> PTS bets are DROPPED (PTS robustly loses to closes), REB/AST
       kept. AST is NOT recalibrated here (raw projection preserved).

  2. CV_SLATE_VAC_BUMP on the slate build path (scripts.cv_fix_build_slate._apply_vac_bump):
     - OFF -> cache q50/q10/q90 unchanged (byte-identical).
     - ON  -> a player whose teammate is OUT tonight gets the validated vacated-load bump
       on the webpage path (the freshness CASE-test; the #1 plumbing gap).

These tests build tiny in-memory slates and never require a live server or network.
"""
from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ──────────────────────────────────────────────────────────────────────────────
# Fix 1 — CV_BET_POLICY on the webpage bet surface
# ──────────────────────────────────────────────────────────────────────────────

def _bet(stat: str, side: str, line: float, q50: float, gid: str = "0022500001") -> dict:
    """Minimal bet card shaped like grade_bet() output, enough for the gate."""
    return {
        "prop_stat": stat.upper(), "side": side, "line": line, "q50": q50,
        "edge_units": round(q50 - line, 3), "game_id": gid,
        "ev_pct": 5.0, "model_prob": 0.6, "best_price": -110,
        "all_books": [{"book": "DraftKings", "price": -110}],
        "kelly_stake_dollars": 1.0, "kelly_pct": 1.0,
    }


def _survivors(envelope: dict) -> set:
    return {(b["prop_stat"], b["side"]) for b in envelope.get("bets") or []}


@pytest.fixture
def _gate_bets():
    """Three bets all chosen to SURVIVE the page's Iter-57 stack:
      PTS OVER 25.5   (line>15.5 not excluded, edge 2.0>=1.0)
      REB UNDER 4.5   (mid bucket allowed, under not the excluded over/low, edge 2.0>=1.5)
      AST UNDER 5.5   (high bucket allowed, under not the excluded over/high, edge 1.5>=1.0)
    """
    return [
        _bet("pts", "OVER", 25.5, 27.5),
        _bet("reb", "UNDER", 4.5, 2.5),
        _bet("ast", "UNDER", 5.5, 4.0),
    ]


@pytest.fixture(autouse=True)
def _clean_policy_env(monkeypatch):
    monkeypatch.delenv("CV_BET_POLICY", raising=False)
    yield


def test_bet_policy_off_is_byte_identical(monkeypatch, _gate_bets):
    """CV_BET_POLICY unset (iter57) -> the webpage gate keeps exactly the bets the
    existing Iter-57 stack keeps. The bet-policy layer is a strict pass-through."""
    monkeypatch.delenv("CV_BET_POLICY", raising=False)
    from api import courtvision_router as cr
    env_off = cr._apply_calibration_gate({"bets": [dict(b) for b in _gate_bets]})
    survivors = _survivors(env_off)
    # All three were constructed to clear the Iter-57 stack; none removed by policy.
    assert ("PTS", "OVER") in survivors
    assert ("REB", "UNDER") in survivors
    assert ("AST", "UNDER") in survivors


def test_bet_policy_reb_ast_drops_pts_keeps_reb_ast(monkeypatch, _gate_bets):
    """CV_BET_POLICY=reb_ast -> PTS dropped (loses to closes), REB+AST kept."""
    monkeypatch.setenv("CV_BET_POLICY", "reb_ast")
    from api import courtvision_router as cr
    env_on = cr._apply_calibration_gate({"bets": [dict(b) for b in _gate_bets]})
    survivors = _survivors(env_on)
    assert ("PTS", "OVER") not in survivors, "reb_ast policy must drop PTS on the webpage"
    assert ("REB", "UNDER") in survivors
    assert ("AST", "UNDER") in survivors


def test_bet_policy_playoff_ast_guard(monkeypatch):
    """CV_BET_POLICY=ast_high on a playoff game (gid 004...) drops AST unless allowed.

    Validates the regime guard is plumbed: AST breaks in playoffs (VS_VEGAS §8e)."""
    monkeypatch.setenv("CV_BET_POLICY", "ast_high")
    from api import courtvision_router as cr
    # AST OVER with edge 2.0 (>=0.75 ast_high min) at line 5.5 (<=7.5 cap), playoff gid.
    b = _bet("ast", "OVER", 5.5, 7.5, gid="0042500401")
    env = cr._apply_calibration_gate({"bets": [b]})
    assert ("AST", "OVER") not in _survivors(env), "playoff AST must be dropped under ast_high"


# ──────────────────────────────────────────────────────────────────────────────
# Fix 2 — CV_SLATE_VAC_BUMP on the slate build path (freshness CASE-test)
# ──────────────────────────────────────────────────────────────────────────────

def _toy_cache():
    """Active MEM player STAR only — mirrors the real flow where OUT players are
    already dropped from the cache before _apply_vac_bump runs (cv_fix_build_slate
    drops + redistributes OUT players first). pandas frame shaped like
    predictions_cache_<date>.parquet."""
    import pandas as pd
    rows = []
    for stat, q50, q10, q90 in [
        ("pts", 20.0, 14.0, 26.0), ("ast", 6.0, 3.0, 9.0), ("reb", 5.0, 3.0, 7.0),
    ]:
        rows.append({"player_id": 101, "player_name": "Star Active", "team": "MEM",
                     "stat": stat, "q50": q50, "q10": q10, "q90": q90,
                     "sigma": round((q90 - q10) / 2.5631, 3)})
    return pd.DataFrame(rows)


def _stub_vac_map(monkeypatch, *, sitter_out: bool):
    """Patch the availability layer so the test never reads disk / injury feeds.
    When sitter_out=True, MEM has the SITTER ruled out (vac_pts>0)."""
    import scripts.cv_fix_build_slate as cfs
    from src.prediction import availability as avail

    def _fake_team_vacated_map(date, resolve_pid, season="2025-26"):
        if not sitter_out:
            return {}
        # SITTER's L10 ~ 22 pts / 30 min — a real regular whose absence frees usage.
        return {"MEM": {"vac_min": 30.0, "vac_pts": 22.0, "n_out": 1}}

    monkeypatch.setattr(avail, "team_vacated_map", _fake_team_vacated_map, raising=True)
    return cfs


def test_vac_bump_off_is_byte_identical(monkeypatch):
    """CV_SLATE_VAC_BUMP unset -> cache returned UNCHANGED even when a teammate is OUT."""
    monkeypatch.delenv("CV_SLATE_VAC_BUMP", raising=False)
    cfs = _stub_vac_map(monkeypatch, sitter_out=True)
    cache = _toy_cache()
    before = cache.copy(deep=True)
    n = cfs._apply_vac_bump(cache, "2026-06-04")
    assert n == 0, "flag OFF must be a strict no-op"
    import pandas as pd
    pd.testing.assert_frame_equal(cache, before)


def test_vac_bump_on_bumps_teammate_out_player(monkeypatch):
    """FRESHNESS CASE-TEST: CV_SLATE_VAC_BUMP=1 + STAR's teammate OUT -> STAR's
    usage-driven q50 (pts/ast) is bumped UP on the webpage build path."""
    monkeypatch.setenv("CV_SLATE_VAC_BUMP", "1")
    cfs = _stub_vac_map(monkeypatch, sitter_out=True)
    cache = _toy_cache()

    def _q(stat):
        m = (cache["player_id"] == 101) & (cache["stat"] == stat)
        return float(cache.loc[m, "q50"].iloc[0])

    pts0, ast0, reb0 = _q("pts"), _q("ast"), _q("reb")
    n = cfs._apply_vac_bump(cache, "2026-06-04")
    assert n == 1, "exactly the one active MEM player should be bumped"
    assert _q("pts") > pts0, "usage stat PTS must rise when a teammate is OUT"
    assert _q("ast") > ast0, "usage stat AST must rise when a teammate is OUT"
    # REB is opportunity-driven (smaller k) — still non-decreasing.
    assert _q("reb") >= reb0


def test_vac_bump_on_no_out_is_noop(monkeypatch):
    """CV_SLATE_VAC_BUMP=1 but NOBODY out tonight -> cache unchanged (empty vac map)."""
    monkeypatch.setenv("CV_SLATE_VAC_BUMP", "1")
    cfs = _stub_vac_map(monkeypatch, sitter_out=False)
    cache = _toy_cache()
    before = cache.copy(deep=True)
    n = cfs._apply_vac_bump(cache, "2026-06-04")
    assert n == 0
    import pandas as pd
    pd.testing.assert_frame_equal(cache, before)


def test_vac_bump_scales_quantiles_consistently(monkeypatch):
    """When q50 is bumped, q10/q90/sigma scale by the SAME ratio so CV_ROW_SIGMA stays
    self-consistent (the per-row band keeps its shape)."""
    monkeypatch.setenv("CV_SLATE_VAC_BUMP", "1")
    cfs = _stub_vac_map(monkeypatch, sitter_out=True)
    cache = _toy_cache()
    m = (cache["player_id"] == 101) & (cache["stat"] == "pts")
    q50_0 = float(cache.loc[m, "q50"].iloc[0])
    q90_0 = float(cache.loc[m, "q90"].iloc[0])
    cfs._apply_vac_bump(cache, "2026-06-04")
    q50_1 = float(cache.loc[m, "q50"].iloc[0])
    q90_1 = float(cache.loc[m, "q90"].iloc[0])
    ratio_q50 = q50_1 / q50_0
    ratio_q90 = q90_1 / q90_0
    assert abs(ratio_q50 - ratio_q90) < 1e-3, "q90 must scale by the same ratio as q50"
