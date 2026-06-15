"""Tests for the in-game live read (scripts/platformkit/live_read.py).

Honest invariants: the live read fuses the gate-owned re-priced surface with
descriptive in-game brain concepts; edge_claimed is always False; the rendered doc is
person-free / no-edge (brain_audit clean); surfaced concepts come from in-game families.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.platformkit.live_read import build_live_read, render_markdown, _INGAME_FAMILIES
from scripts.platformkit.live_repricer import GameState
from scripts.platformkit.brain_audit import scan_text

_CASES = {
    "nba": GameState(sport="nba", elapsed_minutes=36.0, home_score=82, away_score=78,
                     pregame_params={"mu_home": 114, "mu_away": 112}),
    "mlb": GameState(sport="mlb", elapsed_minutes=0.0, home_score=3, away_score=2,
                     pregame_params={"lam_home": 4.6, "lam_away": 4.3},
                     extra={"innings_played": 6}),
    "soccer": GameState(sport="soccer", elapsed_minutes=70.0, home_score=1, away_score=1,
                        pregame_params={"lam_home": 1.6, "lam_away": 1.2}),
    "tennis": GameState(sport="tennis", elapsed_minutes=0.0, home_score=0, away_score=0,
                        pregame_params={"best_of": 3, "p_set": 0.55},
                        extra={"sets_1": 1, "sets_2": 0}),
}


@pytest.mark.parametrize("sport", list(_CASES))
def test_build_has_surface_and_no_edge(sport):
    read = build_live_read(sport, _CASES[sport])
    assert read["sport"] == sport
    assert read["edge_claimed"] is False
    assert isinstance(read["surface"], dict) and read["surface"]
    assert "ingame_concepts" in read


@pytest.mark.parametrize("sport", list(_CASES))
def test_render_audit_clean(sport):
    md = render_markdown(build_live_read(sport, _CASES[sport]))
    assert "Live Read" in md
    assert "Re-priced surface" in md
    assert scan_text(md) == [], f"audit flags for {sport}: {scan_text(md)}"


@pytest.mark.parametrize("sport", list(_CASES))
def test_concepts_are_ingame_family(sport):
    read = build_live_read(sport, _CASES[sport])
    for c in read["ingame_concepts"]:
        assert c["family"].lower() in _INGAME_FAMILIES, (
            f"{sport}: {c['family']} not an in-game family")


def test_nba_surface_reflects_lead():
    """A home lead late should put home win prob well above 0.5."""
    read = build_live_read("nba", _CASES["nba"])
    assert read["surface"]["win_home"] > 0.6


def test_unknown_sport_degrades_gracefully():
    st = GameState(sport="cricket", elapsed_minutes=10.0, home_score=1, away_score=0)
    read = build_live_read("cricket", st)
    assert read["edge_claimed"] is False
    # repricer returns a not_wired stub; render must not crash
    md = render_markdown(read)
    assert "Live Read" in md
