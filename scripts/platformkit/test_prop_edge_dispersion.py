"""Per-file tests: NB width calibration + EV honesty guard in the prop board.

  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_prop_edge_dispersion.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.soccer import prop_engine
from scripts.platformkit import prop_edge
from scripts.platformkit.odds_provider.prop_base import PropLine


def test_negbin_widens_high_line_tail():
    """For an over-dispersed stat (phi>1), NB p_over at a HIGH line is LARGER than
    Poisson -- the wider tail shrinks the absurd Poisson EV. Hand-checked vs the
    real pmf in prop_engine."""
    lam = 2.0
    df = pd.DataFrame()  # not used: we drive prop_distribution directly via lam
    # Poisson (no dispersion) vs NB with size r derived from phi=1.6 at lam=2.0.
    # r = lam/(phi-1) = 2.0/0.6 = 3.333.
    pois = prop_engine._make_p_over(lam, "poisson", None)
    nb = prop_engine._make_p_over(lam, "negbin", lam / 0.6)
    # High line well above the mean -> NB (heavier tail) must give MORE prob over.
    for line in (4.5, 5.5, 6.5):
        assert nb(line) > pois(line), line
    assert df.empty  # silence lint: df intentionally unused placeholder


def _df():
    """Resolvable player with > _MIN_N? No -- thin by design for the flag test, and
    a separate non-thin player for the reliable-ranking test."""
    rows = []
    # 'Thin Star': only ONE prior match -> confidence thin.
    rows.append({"player_id": "300", "player": "Thin Star", "team_abbr": "ARG",
                 "position": "F", "starter": True, "minutes": 90, "totalShots": 8,
                 "shotsOnTarget": 4, "date": "2026-06-01"})
    # 'Solid Mid': two prior matches, not shrunk-to-baseline -> confidence ok.
    for d in ("2026-06-01", "2026-06-05"):
        rows.append({"player_id": "400", "player": "Solid Mid", "team_abbr": "BRA",
                     "position": "F", "starter": True, "minutes": 90,
                     "totalShots": 3, "shotsOnTarget": 1, "date": d})
        rows.append({"player_id": "401", "player": "Other Mid", "team_abbr": "BRA",
                     "position": "F", "starter": True, "minutes": 90,
                     "totalShots": 2, "shotsOnTarget": 1, "date": d})
    return pd.DataFrame(rows)


def _lines():
    thin = PropLine(
        sport="soccer_intl", event_id="t1", match="ARG v BRA",
        player="Thin Star", team="ARG", stat="Shots", line=0.5,
        over_price=1.90, under_price=1.90, payout_type="sportsbook",
        source="underdog")
    solid = PropLine(
        sport="soccer_intl", event_id="s1", match="ARG v BRA",
        player="Solid Mid", team="BRA", stat="Shots", line=2.5,
        over_price=1.90, under_price=1.90, payout_type="sportsbook",
        source="underdog")
    return [thin, solid]


def test_edges_carry_flags_and_model():
    board = prop_edge.build_prop_board(
        "soccer_intl", as_of="2026-06-11", df=_df(), lines_source=_lines())
    assert board["status"] == "ok"
    edges = board["edges"]
    assert len(edges) == 2
    for e in edges:
        assert "ev_flag" in e and e["ev_flag"] in (
            "ok", "uncalibrated_thin", "implausible")
        assert "dispersion_phi" in e
        assert e["model"] in ("poisson", "negbin")
        assert isinstance(e["reliable"], bool)


def test_thin_edge_flagged_uncalibrated():
    board = prop_edge.build_prop_board(
        "soccer_intl", as_of="2026-06-11", df=_df(), lines_source=_lines())
    thin = next(e for e in board["edges"] if e["player"] == "Thin Star")
    assert thin["confidence"] == "thin"
    assert thin["reliable"] is False
    assert thin["ev_flag"] == "uncalibrated_thin"


def test_reliable_ranks_above_flagged():
    board = prop_edge.build_prop_board(
        "soccer_intl", as_of="2026-06-11", df=_df(), lines_source=_lines())
    edges = board["edges"]
    # The reliable (ok-flag) edge must rank above any flagged edge.
    flagged_idx = [i for i, e in enumerate(edges)
                   if e["ev_flag"] != "ok" or not e["reliable"]]
    reliable_idx = [i for i, e in enumerate(edges)
                    if e["ev_flag"] == "ok" and e["reliable"]]
    if reliable_idx and flagged_idx:
        assert max(reliable_idx) < min(flagged_idx)


def test_implausible_ev_flagged():
    """An over-dispersed model can still produce an outsized EV on a soft line; an
    |EV|>0.5 must be flagged 'implausible' (an artifact), not silently trusted."""
    flag = prop_edge._ev_flag("ok", 1.31)   # +131% EV
    assert flag == "implausible"
    assert prop_edge._ev_flag("ok", -0.6) == "implausible"
    assert prop_edge._ev_flag("ok", 0.2) == "ok"
    assert prop_edge._ev_flag("thin", 0.2) == "uncalibrated_thin"
    assert prop_edge._ev_flag("ok", None) == "ok"
