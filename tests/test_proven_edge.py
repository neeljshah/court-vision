"""Tests for proven_edge_card + sgp_edge_scanner — pure logic, no sim/network.

Py3.9, type hints. Fake result engineered so:
  - one same_player pair is positively correlated (lift>1)
  - one teammate all-over pts pair is negatively correlated (lift<1)

Board:
    python -m pytest tests/test_proven_edge.py -q
"""
from __future__ import annotations

import os
import sys
import types
from typing import Any
from unittest.mock import patch

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "team_system"))
sys.path.insert(0, os.path.join(ROOT, "src"))

import sgp_edge_scanner as ses
import proven_edge_card as pec
from proven_edge_card import (
    CardEdge, RefusedCandidate,
    _PROVEN_KINDS, _REFUSE_SOURCES,
    refuse_artifact_edges, build_proven_edge_card, render_card, BANNER, HONESTY_CLASS,
)
from sgp_edge_scanner import SgpEdge, SGP_STATUS, scan_sgp_edges, _basket_type, describe_scan


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _fake_result() -> Any:
    """2 players on 1 team + 1 cross-team player.
    Engineered samples:
      - pid=1: pts and ast are POSITIVELY correlated (both high or both low)
        -> same_player (pts,ast) lift > 1
      - pid=2 (teammate): negatively correlated pts with pid=1 (shared pie)
        -> teammate all-over stack lift < 1
      - pid=3 (cross-team): weakly correlated with pid=1
    """
    rng = np.random.default_rng(42)
    n = 4000

    # pid=1: pts ~ N(20,5), ast = 0.8*pts + noise (positive correlation)
    pts1_base = rng.normal(20, 5, n)
    pts1 = np.clip(pts1_base, 0, None).astype(float)
    ast1 = np.clip(0.8 * pts1_base + rng.normal(0, 2, n), 0, None).astype(float)
    reb1 = np.clip(rng.normal(4, 1.5, n), 0, None).astype(float)

    # pid=2: pts = 40 - pts1 + noise (negatively correlated -- shared pie)
    pts2 = np.clip(40 - pts1_base + rng.normal(0, 3, n), 0, None).astype(float)
    ast2 = np.clip(rng.normal(5, 2, n), 0, None).astype(float)
    reb2 = np.clip(rng.normal(6, 2, n), 0, None).astype(float)

    # pid=3: cross-team, independent
    pts3 = np.clip(rng.normal(18, 5, n), 0, None).astype(float)
    ast3 = np.clip(rng.normal(3, 1.5, n), 0, None).astype(float)
    reb3 = np.clip(rng.normal(8, 2, n), 0, None).astype(float)

    result = types.SimpleNamespace()
    result.players = {
        1: {
            "name": "FakePlayer A",
            "team": "NYK",
            "mean": {"pts": float(pts1.mean()), "reb": float(reb1.mean()), "ast": float(ast1.mean())},
            "q10": {"pts": float(np.percentile(pts1, 10))},
            "q50": {"pts": float(np.median(pts1))},
            "q90": {"pts": float(np.percentile(pts1, 90))},
            "samples": {"pts": pts1, "reb": reb1, "ast": ast1},
        },
        2: {
            "name": "FakePlayer B",
            "team": "NYK",
            "mean": {"pts": float(pts2.mean()), "reb": float(reb2.mean()), "ast": float(ast2.mean())},
            "q10": {"pts": float(np.percentile(pts2, 10))},
            "q50": {"pts": float(np.median(pts2))},
            "q90": {"pts": float(np.percentile(pts2, 90))},
            "samples": {"pts": pts2, "reb": reb2, "ast": ast2},
        },
        3: {
            "name": "FakePlayer C",
            "team": "SAS",
            "mean": {"pts": float(pts3.mean()), "reb": float(reb3.mean()), "ast": float(ast3.mean())},
            "q10": {"pts": float(np.percentile(pts3, 10))},
            "q50": {"pts": float(np.median(pts3))},
            "q90": {"pts": float(np.percentile(pts3, 90))},
            "samples": {"pts": pts3, "reb": reb3, "ast": ast3},
        },
    }
    return result


# ---------------------------------------------------------------------------
# SGP scanner tests
# ---------------------------------------------------------------------------

def test_scan_ranks_by_abs_lift_error():
    res = _fake_result()
    edges = scan_sgp_edges(res, top_n=20, min_pts_mean=5.0)
    assert len(edges) >= 2
    errs = [e.abs_lift_error for e in edges]
    assert errs == sorted(errs, reverse=True), "edges must be sorted desc by abs_lift_error"


def test_scan_direction_take_when_lift_gt1():
    """Positively correlated same_player (pts,ast) for pid=1 should have lift>1 -> direction='take'."""
    res = _fake_result()
    edges = scan_sgp_edges(res, top_n=30, min_pts_mean=5.0)
    # find same_player (pts,ast) edge for pid=1
    target = [
        e for e in edges
        if e.basket_type == "same_player"
        and any(lg.pid == 1 and lg.stat == "pts" for lg in e.legs)
        and any(lg.pid == 1 and lg.stat == "ast" for lg in e.legs)
    ]
    assert target, "expected same_player pts+ast edge for pid=1"
    e = target[0]
    assert e.lift > 1.0, f"expected lift>1 for positively correlated player, got {e.lift}"
    assert e.direction == "take"


def test_scan_direction_fade_when_lift_lt1():
    """Teammate all-over pts pair (pid=1 and pid=2) should be negatively correlated -> direction='fade'."""
    res = _fake_result()
    edges = scan_sgp_edges(res, top_n=30, min_pts_mean=5.0)
    target = [
        e for e in edges
        if e.basket_type == "teammate"
        and {lg.pid for lg in e.legs} == {1, 2}
    ]
    assert target, "expected teammate pts pair edge for pids 1+2"
    e = target[0]
    assert e.lift < 1.0, f"expected lift<1 for teammate pie, got {e.lift}"
    assert e.direction == "fade"


def test_scan_every_edge_status_pending():
    res = _fake_result()
    edges = scan_sgp_edges(res, top_n=20, min_pts_mean=5.0)
    for e in edges:
        assert e.status == "VALIDATED-STRUCTURE-ROI-PENDING", f"wrong status: {e.status}"


def test_scan_respects_top_n():
    res = _fake_result()
    for top_n in [1, 3, 7]:
        edges = scan_sgp_edges(res, top_n=top_n, min_pts_mean=5.0)
        assert len(edges) <= top_n, f"expected <= {top_n} edges, got {len(edges)}"


def test_basket_type_classification():
    res = _fake_result()
    from sim.sgp_from_sim import Leg
    # same_player
    legs_sp = [Leg(1, "pts", 20.0), Leg(1, "ast", 5.0)]
    assert _basket_type(res, legs_sp) == "same_player"
    # teammate
    legs_tm = [Leg(1, "pts", 20.0), Leg(2, "pts", 18.0)]
    assert _basket_type(res, legs_tm) == "teammate"
    # cross_team
    legs_ct = [Leg(1, "pts", 20.0), Leg(3, "pts", 18.0)]
    assert _basket_type(res, legs_ct) == "cross_team"


# ---------------------------------------------------------------------------
# HARD GUARD tests
# ---------------------------------------------------------------------------

def test_guard_refuses_model_vs_line():
    bad = {"kind": "model_marginal_vs_line", "source": "model_marginal_vs_line",
           "headline": "model beats line on PTS", "detail": {}}
    kept, refused = refuse_artifact_edges([bad])
    assert bad not in kept
    assert len(refused) == 1
    assert refused[0].status == "REFUSED-ARTIFACT"


def test_guard_refuses_all_refuse_sources():
    for src in _REFUSE_SOURCES:
        bad = {"kind": src, "source": src, "headline": "test", "detail": {}}
        kept, refused = refuse_artifact_edges([bad])
        assert not kept, f"expected empty kept for source={src}"
        assert len(refused) == 1, f"expected 1 refused for source={src}"


def test_guard_keeps_proven_kinds():
    for kind in _PROVEN_KINDS:
        good = CardEdge(kind=kind, status="TEST", headline="test", detail={})
        kept, refused = refuse_artifact_edges([good])
        assert good in kept, f"expected {kind} to be kept"
        assert not refused


def test_guard_playoff_reason_cited():
    bad = {"kind": "model_marginal_vs_line", "source": "model_marginal_vs_line",
           "headline": "playoff model edge", "detail": {}}
    _, refused = refuse_artifact_edges([bad], is_playoff=True)
    assert refused
    assert "PLAYOFF" in refused[0].reason or "playoff" in refused[0].reason.lower()
    assert "-2%" in refused[0].reason or "2%" in refused[0].reason


def test_guard_records_reason_never_silent():
    bad = {"kind": "model_vs_line", "source": "model_vs_line", "headline": "test", "detail": {}}
    _, refused = refuse_artifact_edges([bad], is_playoff=False)
    assert refused[0].reason, "reason must be non-empty (never silent)"
    _, refused_po = refuse_artifact_edges([bad], is_playoff=True)
    assert refused_po[0].reason, "playoff reason must be non-empty"


def test_guard_refused_have_status_tag():
    bad = {"kind": "marginal_vs_book", "source": "marginal_vs_book", "headline": "test", "detail": {}}
    _, refused = refuse_artifact_edges([bad])
    for r in refused:
        assert r.status == "REFUSED-ARTIFACT"


# ---------------------------------------------------------------------------
# Card composition tests
# ---------------------------------------------------------------------------

def test_card_honesty_class_paper():
    res = _fake_result()
    card = build_proven_edge_card("NYK", "SAS", result=res, sgp_top_n=3)
    assert card["honesty_class"] == "paper"
    for e in card["edges"]:
        assert e.honesty_class == "paper", f"edge {e.kind} missing honesty_class=paper"


def test_card_has_banner():
    card = build_proven_edge_card("NYK", "SAS")
    assert "banner" in card
    banner = card["banner"].lower()
    assert "paper" in banner or "display" in banner


def test_line_shop_edge_deterministic():
    card = build_proven_edge_card("NYK", "SAS")
    ls_edges = [e for e in card["edges"] if e.kind == "LINE_SHOP"]
    assert ls_edges, "LINE_SHOP edge must always be present"
    e = ls_edges[0]
    assert e.status == "PROVEN-DETERMINISTIC"
    ev = e.detail.get("ev_per_bet", 0)
    assert abs(ev - 0.035) < 0.01, f"LINE_SHOP ev {ev} should be ~0.035"


def test_freshness_emitted_only_on_trigger():
    # trigger=True -> FRESHNESS edge emitted
    trigger_response = {
        "freshness_trigger": True,
        "regseason_ceiling": 0.579,
        "playoff_ceiling": 0.548,
        "situations": [{"player": "TestPlayer", "team": "NYK", "status": "OUT",
                        "rotation_significant": True, "mpg": 28.0, "reason": "knee"}],
    }
    no_trigger_response = {"freshness_trigger": False, "situations": []}

    with patch("proven_edge_card.fm.assess", return_value=trigger_response):
        card = build_proven_edge_card("NYK", "SAS")
        fresh = [e for e in card["edges"] if e.kind == "FRESHNESS"]
        assert fresh, "FRESHNESS edge should be emitted on trigger"

    with patch("proven_edge_card.fm.assess", return_value=no_trigger_response):
        card = build_proven_edge_card("NYK", "SAS")
        fresh = [e for e in card["edges"] if e.kind == "FRESHNESS"]
        assert not fresh, "FRESHNESS edge must NOT be emitted when trigger=False"

    with patch("proven_edge_card.fm.assess", return_value={"status": "no-feed"}):
        card = build_proven_edge_card("NYK", "SAS")
        fresh = [e for e in card["edges"] if e.kind == "FRESHNESS"]
        assert not fresh, "FRESHNESS edge must NOT be emitted when no feed"


def test_card_never_emits_model_vs_line():
    """Inject a model-vs-line extra_candidate -> must appear in refused, never in edges."""
    bad = {"kind": "model_marginal_vs_line", "source": "model_marginal_vs_line",
           "headline": "PTS model beats line +2%", "detail": {}}
    card = build_proven_edge_card("NYK", "SAS", extra_candidates=[bad], is_playoff=True)
    edge_kinds = [e.kind for e in card["edges"]]
    assert "model_marginal_vs_line" not in edge_kinds
    refused_sources = [r.source for r in card["refused"]]
    assert "model_marginal_vs_line" in refused_sources


def test_card_edges_kind_in_allowlist():
    res = _fake_result()
    card = build_proven_edge_card("NYK", "SAS", result=res, sgp_top_n=5)
    for e in card["edges"]:
        assert e.kind in _PROVEN_KINDS, f"edge kind {e.kind!r} not in allowed list"


# ---------------------------------------------------------------------------
# CRITICAL: the planted Brunson model-vs-line edge must be REFUSED (playoff)
# ---------------------------------------------------------------------------

def test_guard_refuses_planted_brunson_model_edge_playoff():
    """The whole point of the module: a 'model beats book line on Brunson pts by +8%'
    candidate is the disproven artifact. It MUST be refused for a playoff game with a
    recorded reason citing the playoff artifact magnitude (-2% to -5%)."""
    planted = {
        "kind": "point_model_edge",
        "source": "model_marginal_vs_line",
        "provenance": "marginal",
        "headline": "model beats book line on Brunson pts by +8%",
        "detail": {"player": "Jalen Brunson", "stat": "pts", "edge_pct": 0.08},
    }
    kept, refused = refuse_artifact_edges([planted], is_playoff=True)
    assert not kept, "planted Brunson model-vs-line edge must NOT be kept"
    assert len(refused) == 1
    r = refused[0]
    assert r.status == "REFUSED-ARTIFACT"
    assert r.reason, "refusal reason must be recorded, never silent"
    assert "PLAYOFF" in r.reason or "playoff" in r.reason.lower()
    assert "-2%" in r.reason or "2%" in r.reason, "playoff reason must cite the -2% to -5% artifact"


def test_guard_refuses_planted_edge_even_with_novel_kind():
    """Defense-in-depth: even if the artifact arrives with an UNKNOWN kind (not in the
    refuse-source allowlist), the kind-not-in-_PROVEN_KINDS rule still refuses it. An
    unknown candidate can never silently become an emitted edge."""
    sneaky = {"kind": "SOME_NEW_POINT_EDGE",
              "headline": "model beats line +8% on Brunson pts", "detail": {}}
    kept, refused = refuse_artifact_edges([sneaky], is_playoff=True)
    assert not kept
    assert len(refused) == 1 and refused[0].reason


def test_card_never_emits_planted_brunson_edge_end_to_end():
    """Full card path: plant the Brunson model edge as an extra_candidate and assert the
    card emits ONLY proven kinds and logs the artifact in refused (playoff)."""
    planted = {
        "kind": "point_model_edge",
        "source": "model_marginal_vs_line",
        "provenance": "marginal",
        "headline": "model beats book line on Brunson pts by +8%",
        "detail": {},
    }
    card = build_proven_edge_card("NYK", "SAS", extra_candidates=[planted], is_playoff=True)
    for e in card["edges"]:
        assert e.kind in _PROVEN_KINDS, f"point-model edge leaked into card as {e.kind!r}"
    assert card["refused"], "planted artifact must be recorded in refused"
    assert any("model_marginal_vs_line" in r.source or "point_model_edge" in r.source
               for r in card["refused"]), "planted Brunson edge must appear in refused log"
